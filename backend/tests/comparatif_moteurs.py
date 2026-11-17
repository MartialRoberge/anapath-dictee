"""Comparatif LIVE ancien moteur / nouveau moteur (Mistral reel), memes dictees, memes attentes.

Usage (depuis backend/) :
    ../venv/bin/python tests/comparatif_moteurs.py --executer --sortie /chemin/hors/depot/brut.json [--parallele 3]
        [--cas id1,id2] [--moteurs ancien,nouveau] [--isole 10]
    ../venv/bin/python tests/comparatif_moteurs.py --analyser /chemin/brut.json[,/chemin/brut2.json]

Deux phases separees : --executer appelle Mistral et ecrit les sorties NORMALISEES (aucune metrique) ; --analyser
calcule toutes les mesures a partir de ce fichier, sans appel reseau (on peut donc raffiner une metrique sans
repayer les appels). Le fichier brut contient les dictees de test (synthetiques) : ne pas le deposer dans le depot.

Moteurs :
  ancien  = reports/ (REPORT_ENGINE=multipass) : MultiPassReportEngine.generate() + reports.panel.build_panel()
            + adicap.suggerer_adicap(), c.-a-d. ce que le front historique obtient avec POST /format puis /adicap ;
  nouveau = projet/orchestrateur.Pipeline.executer(dictee=...), c.-a-d. POST /v3/projets?stream=false.

Jeu de test : les dictees ET attentes ecrites d'avance de campagne_v3_adversariale.CAS (59) + 2 cas de
campagne_v3.CAS (phonetique STT, ganglions incoherents) + 6 cas CAS_MANQUANTS (champs obligatoires omis, pour le
rappel des manquants, que le jeu existant ne mesure pas). Les attentes ne sont jamais ajustees.

Les attentes sont evaluees par UN SEUL evaluateur, applique a la vue normalisee des deux moteurs. Quand le moteur
ancien n'expose pas la structure (types d'alerte, trous), la regle est volontairement la plus indulgente pour lui :
le motif d'une alerte attendue est cherche dans TOUS ses signaux (avertissements, relecture, coherence, college),
quel que soit leur type.
"""
from __future__ import annotations

import argparse
import asyncio
import contextvars
import json
import re
import statistics
import sys
import time
from collections import defaultdict
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from text_utils import normaliser  # noqa: E402

TIMEOUT_S = 240
LATENCE_MAX_MS = 90_000
TARIFS = {"entree": 0.5, "sortie": 1.5}  # USD / million de jetons, indicatif (cf. campagne_v3_adversariale)


# ====================================================================================== jeu de test
def charger_cas() -> list[dict]:
    from campagne_v3 import CAS as CAS3
    from campagne_v3_adversariale import CAS as CAS_ADV
    cas = [dict(c) for c in CAS_ADV]
    # Cas de campagne_v3 non couverts par l'adversariale : phonetique STT et incoherence ganglions.
    cas.append({"id": "v3_stt_phonetique", "domaine": "phonetique",
                "dictee": next(c for c in CAS3 if c["id"] == "stt_phonetique")["dictee"],
                "organes_any": ["organe:prostate"],
                "corrections": [r"gleason", r"tumeur|tu meurs"], "requis": [r"gleason", r"3 ?\+ ?4|3 plus 4"],
                "interdits": [r"glison", r"tu meurs"]})
    cas.append({"id": "v3_ganglions_incoherents", "domaine": "incoherence",
                "dictee": next(c for c in CAS3 if c["id"] == "ganglions_incoherents")["dictee"],
                "alertes": [("incoherence", None)]})
    cas.extend(CAS_MANQUANTS)
    return cas


#: Champs obligatoires manquants (rappel). Ecrits AVANT execution, d'apres les donnees minimales INCa/SFP :
#: la dictee omet volontairement des champs qui, selon les referentiels, doivent figurer au compte rendu.
CAS_MANQUANTS: list[dict] = [
    {"id": "manq_sein_biopsie", "domaine": "manquants",
     "dictee": ("Microbiopsies du sein droit, trois carottes. Carcinome infiltrant de type non spécifique, grade SBR 2 "
                "avec trois plus deux plus un. Pas d'emboles."),
     "trous": [r"recepteur.*oestrog|oestrogene|\bre\b", r"her ?2", r"ki ?-?67|proliferation"]},
    {"id": "manq_colon_piece", "domaine": "manquants",
     "dictee": ("Colectomie sigmoïdienne. Tumeur de trente-cinq millimètres. Adénocarcinome moyennement différencié "
                "infiltrant la sous-séreuse."),
     "trous": [r"ganglion", r"marge|limite|recoupe|tranche", r"embol|vasculaire|veineu"]},
    {"id": "manq_prostate_biopsie", "domaine": "manquants",
     "dictee": "Biopsies prostatiques, six carottes. Adénocarcinome acineux sur deux carottes.",
     "trous": [r"gleason", r"longueur|pourcentage|etendue|extension"]},
    {"id": "manq_melanome", "domaine": "manquants",
     "dictee": "Exérèse cutanée du bras. Mélanome à extension superficielle. Marge latérale à trois millimètres.",
     "trous": [r"breslow|epaisseur", r"ulcerat", r"mitos|mitot"]},
    {"id": "manq_thyroide_piece", "domaine": "manquants",
     "dictee": "Thyroïdectomie totale. Carcinome papillaire de quinze millimètres du lobe gauche.",
     "trous": [r"marge|limite|exerese", r"embol|vasculaire|invasion", r"ganglion|extension|capsule"]},
    {"id": "manq_poumon_biopsie", "domaine": "manquants",
     "dictee": "Biopsies bronchiques. Adénocarcinome infiltrant d'architecture acineuse.",
     "trous": [r"ttf|immunohisto|marqueur", r"pd-? ?l ?1|pdl"]},
]


# ====================================================================================== executeurs
_COMPTEUR: contextvars.ContextVar[dict | None] = contextvars.ContextVar("compteur", default=None)


class _ProviderCompte:
    """Proxy du fournisseur LLM de l'ancien moteur : compte appels (tentatives comprises), jetons, echecs."""

    def __init__(self, reel) -> None:
        self._reel = reel
        self.name = reel.name
        self.model = reel.model

    async def complete(self, request):
        c = _COMPTEUR.get()
        if c is not None:
            c["appels"] += 1
        try:
            rep = await self._reel.complete(request)
        except Exception:
            if c is not None:
                c["echecs"] += 1
            raise
        if c is not None:
            c["tok_in"] += int(rep.usage.get("prompt_tokens", 0))
            c["tok_out"] += int(rep.usage.get("completion_tokens", 0))
        return rep

    async def aclose(self) -> None:
        await self._reel.aclose()


_CTX_MAP = {"infiltrant": "malin", "pre_cancereux": "precancereux", "benin": "benin", "indetermine": "indetermine"}
_MARQUEUR = re.compile(r"\[A COMPLETER\s*:?\s*([^\]]*)\]", re.I)


def _texte_plat(cr: str) -> tuple[str, str]:
    """(titre, texte) du CR de l'ancien moteur, sans markdown ni marqueurs de trou."""
    sans_marq = "\n".join(l for l in cr.splitlines() if not _MARQUEUR.search(l) or re.sub(_MARQUEUR, "", l).strip())
    sans_marq = _MARQUEUR.sub("", sans_marq)
    plat = re.sub(r"[*_#]+", "", sans_marq)
    lignes = [l.strip() for l in plat.splitlines() if l.strip()]
    titre = lignes[0] if lignes else ""
    return titre, "\n".join(lignes)


def _categorie_relecture(libelle: str) -> str:
    n = normaliser(libelle)
    if "coher" in n:
        return "incoherence"
    if "fidel" in n:
        return "fidelite"
    if "manqu" in n:
        return "manquant"
    return "autre"


async def executer_ancien(engine, cas: dict) -> dict:
    from adicap import suggerer_adicap
    from reports.panel import build_panel
    from specimen_type import detecter_diagnostic_context
    from etude.extraction import assertions_a_juger
    cpt = {"appels": 0, "tok_in": 0, "tok_out": 0, "echecs": 0}
    _COMPTEUR.set(cpt)
    t0 = time.perf_counter()
    vue: dict = {"moteur": "ancien", "id": cas["id"], "domaine": cas["domaine"], "erreur": None, "timeout": False}
    try:
        r = await asyncio.wait_for(engine.generate(cas["dictee"]), TIMEOUT_S)
    except asyncio.TimeoutError:
        vue.update(erreur="timeout", timeout=True)
    except Exception as exc:  # noqa: BLE001
        vue["erreur"] = f"{type(exc).__name__}: {str(exc)[:200]}"
    vue.update(mur_ms=int((time.perf_counter() - t0) * 1000), appels=cpt["appels"], echecs=cpt["echecs"],
               tok_in=cpt["tok_in"], tok_out=cpt["tok_out"])
    if vue["erreur"]:
        return vue
    titre, texte = _texte_plat(r.cr)
    panel = build_panel(r)
    trous = [m.strip() for m in _MARQUEUR.findall(r.cr) if m.strip()]
    trous += [d.champ for d in panel]
    signaux: list[dict] = []
    for w in r.warnings:
        if w.startswith("Relecture"):
            lib, _, msg = w.partition(":")
            signaux.append({"src": "relecture", "categorie": _categorie_relecture(lib), "gravite": "attention", "message": msg.strip()})
        else:
            info = "retire(s) des suggestions" in w  # journal interne, pas un point a relire
            signaux.append({"src": "garde_fou", "categorie": "autre", "gravite": "info" if info else "attention", "message": w})
    for i in (r.coherence or {}).get("issues", []):
        signaux.append({"src": "coherence", "categorie": "incoherence", "gravite": i.get("severity", "attention"), "message": i.get("message", "")})
    college = (r.trace or {}).get("college")
    soumissions, manques = [], []
    if isinstance(college, dict):
        soumissions = college.get("soumissions", [])
        manques = college.get("manques", [])
        for m in manques:
            signaux.append({"src": "college_manque", "categorie": "manquant", "gravite": "attention",
                            "message": f"{m.get('champ', '')} {m.get('justification', '')}"})
    try:
        n_assertions = len(assertions_a_juger(r.cr, cas["dictee"]))
    except Exception:  # noqa: BLE001
        n_assertions = 0
    try:
        a = suggerer_adicap(r.cr, r.organe)
        adicap = [{"code": a["code"], "organe_code": a["organe_code"], "prelevement_code": a["prelevement_code"],
                   "lesion_code": a["lesion_code"], "libelle": a["lesion"], "statut": "certain" if a.get("confidence") == "haute" else "partiel"}]
    except Exception as exc:  # noqa: BLE001
        adicap = []
        vue["erreur_adicap"] = str(exc)[:100]
    try:
        ctx = _CTX_MAP.get(detecter_diagnostic_context(r.cr).value, "indetermine")
    except Exception:  # noqa: BLE001
        ctx = "indetermine"
    vue.update(
        titre=titre, texte=texte, cr_brut=r.cr, trous=trous, signaux=signaux,
        organes=[o for o in r.organes_detectes] or ([r.organe] if r.organe else []),
        prelevement=r.type_prelevement, contexte=ctx,
        corrections=[], a_relire_elements=[],
        adicap=adicap, college_present=isinstance(college, dict), college_quorum=(college or {}).get("quorum"),
        college_soumissions=[{"assertion": s.get("assertion"), "comportement": s.get("comportement"),
                              "motif": s.get("motif"), "empan": s.get("empan_debut") is not None,
                              "justifications": s.get("justifications", [])} for s in soumissions],
        n_assertions=n_assertions, comprehension=(r.trace or {}).get("comprehension", {}),
        refs_structurees=0, avertissements_bruts=r.warnings,
    )
    return vue


async def executer_nouveau(client, cas: dict) -> dict:
    from projet.orchestrateur import Pipeline
    from projet.referentiel import Referentiel
    t0 = time.perf_counter()
    vue: dict = {"moteur": "nouveau", "id": cas["id"], "domaine": cas["domaine"], "erreur": None, "timeout": False}
    p = None
    try:
        p = await asyncio.wait_for(Pipeline(client, referentiel=Referentiel()).executer(dictee=cas["dictee"]), TIMEOUT_S)
    except asyncio.TimeoutError:
        vue.update(erreur="timeout", timeout=True)
    except Exception as exc:  # noqa: BLE001
        vue["erreur"] = f"{type(exc).__name__}: {str(exc)[:200]}"
    vue["mur_ms"] = int((time.perf_counter() - t0) * 1000)
    if p is None:
        vue.setdefault("appels", 0)
        return vue
    m = p.metriques
    elements = []
    for e in p.elements:
        elements.append({
            "id": e.id, "type": e.type, "texte": e.texte, "statut": e.statut, "confiance": e.confiance,
            "a_verifier": e.a_verifier,
            "sources": [{"kind": s.kind, "libelle": s.libelle, "debut": s.debut, "fin": s.fin, "extrait": s.extrait} for s in e.sources],
            "n_preuves": len(e.preuves),
        })
    alertes = [{"type": a.type, "gravite": a.gravite, "message": a.message, "pourquoi": a.pourquoi, "calcul": a.calcul,
                "action": a.action, "element_ids": a.element_ids, "suggestion": a.suggestion,
                "sources": [{"kind": s.kind, "libelle": s.libelle} for s in a.sources]} for a in p.alertes]
    texte_non_trou = "\n".join(e.texte for e in p.elements if e.type != "trou")
    vue.update(
        appels=m.appels_llm, tok_in=m.tokens_entree, tok_out=m.tokens_sortie, echecs=0,
        titre=p.titre, texte=p.titre + "\n" + texte_non_trou,
        trous=[e.texte for e in p.elements if e.type == "trou"],
        signaux=[{"src": "alerte", "categorie": a.type, "gravite": a.gravite, "message": a.message + " " + a.pourquoi} for a in p.alertes],
        organes=p.contexte.organes, prelevement=p.contexte.prelevement, contexte=p.contexte.contexte_lesionnel,
        niveau_service=p.contexte.niveau_service,
        corrections=[{"original": c.original, "corrige": c.corrige, "confiance": c.confiance, "appliquee": c.appliquee} for c in p.corrections],
        dictee_corrigee=p.dictee.corrigee, elements=elements, alertes=alertes,
        adicap=[{"code": c.code, "organe_code": c.code[2:4] if len(c.code) >= 4 else "", "prelevement_code": c.code[:1],
                 "lesion_code": c.code[4:8], "libelle": c.libelle, "statut": c.statut} for c in p.codes if c.systeme == "ADICAP"],
        snomed=[c.code for c in p.codes if c.systeme == "SNOMED_CT"],
        trace=[{"id": t.id, "statut": t.statut, "duree_ms": t.duree_ms, "modele": t.modele} for t in p.trace],
        confiance_moyenne=m.confiance_moyenne,
    )
    return vue


async def executer(args) -> list[dict]:
    from projet.llm_client import ClientMistral
    from reports.factory import build_report_engine
    cas_tous = charger_cas()
    cas = [c for c in cas_tous if not args.cas or c["id"] in args.cas.split(",")]
    moteurs = args.moteurs.split(",")
    sorties: list[dict] = []
    engine = build_report_engine()
    engine._provider = _ProviderCompte(engine._provider)  # noqa: SLF001
    client = ClientMistral()

    async def lot(nom: str, liste: list[dict], parallele: int, etiquette: str) -> None:
        sem = asyncio.Semaphore(parallele)

        async def un(c: dict) -> dict:
            async with sem:
                v = await (executer_ancien(engine, c) if nom == "ancien" else executer_nouveau(client, c))
                v["phase"] = etiquette
                print(f"[{nom}/{etiquette}] {c['id']} {v['mur_ms']} ms appels={v.get('appels')} "
                      f"{'ERREUR ' + v['erreur'] if v['erreur'] else ''}", flush=True)
                return v
        sorties.extend(await asyncio.gather(*[un(c) for c in liste]))

    for nom in moteurs:
        await lot(nom, cas, args.parallele, "lot")
    if args.isole:
        sous = [c for c in cas if c["id"] in {x["id"] for x in cas[:: max(1, len(cas) // args.isole)][: args.isole]}]
        for nom in moteurs:
            await lot(nom, sous, 1, "isole")
    await ClientMistral.fermer()
    await engine.aclose()
    return sorties


# ====================================================================================== mesures
_NOMBRE_UNITE = re.compile(r"(\d+(?:[.,]\d+)?)\s*(mm|millim[a-z]*|cm|centim[a-z]*|%|pour\s*100|pour\s*cent)(?![a-z])")


def _mesures(texte: str) -> set[tuple[float, str]]:
    """Mesures (valeur ramenee en mm, ou en %) d'un texte ; les nombres en lettres sont convertis par `chiffrer`."""
    from projet.mesures import chiffrer
    t = normaliser(chiffrer(texte))
    res: set[tuple[float, str]] = set()
    for n, u in _NOMBRE_UNITE.findall(t):
        v = float(n.replace(",", "."))
        if u.startswith("c") and not u.startswith("cent") or u.startswith("centim"):
            res.add((round(v * 10, 3), "mm"))
        elif u.startswith("m"):
            res.add((round(v, 3), "mm"))
        else:
            res.add((round(v, 3), "%"))
    return res


_NEG_TERME = re.compile(r"\b(?:pas|sans|absence|absent|aucune?|indemne)\s+(?:d'|de\s+|du\s+|des\s+|d\s+|l'|la\s+|le\s+|les\s+|un\s+|une\s+)?([a-z][a-z\-]{4,})")


def _negations(dictee: str, texte: str) -> dict[str, list[str]]:
    """Termes nies de la dictee, classes dans la sortie : conserve (nie) / perdu (absent) / inverse (affirme, jamais nie)."""
    from negation import mask_negations
    nd = normaliser(dictee)
    nt = normaliser(texte)
    nt_masque = mask_negations(nt)
    termes = {m.group(1) for m in _NEG_TERME.finditer(nd)} - {"lesion", "signe", "autre", "image"}
    # un terme n'est « nie » dans la dictee que s'il n'y est pas aussi affirme ailleurs
    dict_masque = mask_negations(nd)
    termes = {t for t in termes if t not in dict_masque}
    out = {"conserve": [], "perdu": [], "inverse": []}
    for t in sorted(termes):
        if t not in nt and t[:-1] not in nt:
            out["perdu"].append(t)
        elif re.search(rf"(?<![a-z]){re.escape(t[:5])}", nt_masque) and not _masque_present(t, nt, nt_masque):
            out["inverse"].append(t)
        else:
            out["conserve"].append(t)
    return out


def _masque_present(terme: str, nt: str, nt_masque: str) -> bool:
    """Vrai si le terme apparait au moins une fois NIE dans le texte (present dans nt, blanchi dans nt_masque)."""
    for m in re.finditer(rf"(?<![a-z]){re.escape(terme[:5])}", nt):
        if nt_masque[m.start():m.start() + 5].strip() == "":
            return True
    return False


def violations_texte(v: dict, dictee: str) -> list[str]:
    """Controles deterministes de fidelite, memes fonctions pour les deux moteurs (V2, V3, negations inversees)."""
    from projet.mesures import chiffrer
    from reports.numbers import chiffres_non_dictes, source_number_set
    res: list[str] = []
    texte = v["texte"]
    dictee_n = dictee + "\n" + chiffrer(dictee)
    nombres = source_number_set(dictee_n)
    if chiffres_non_dictes(texte, dictee_n):
        res.append("V2 chiffre non dicte : " + ", ".join(chiffres_non_dictes(texte, dictee_n)))
    texte_num = re.sub(r"(?m)^\s*\d{1,2}\s*[).°-]", "", texte)
    for n in re.findall(r"(?<![A-Za-z0-9\-/])\d+(?:[.,]\d+)?(?![A-Za-z0-9])", texte_num):
        if not all(x in nombres for x in re.split(r"[.,]", n)):
            res.append(f"V2 nombre non dicte : {n}")
    for t in re.findall(r"\b(?:y?p|c)?[TNM](?:is|[0-4xX])[a-d]?\b", texte):
        if normaliser(t) not in normaliser(dictee):
            res.append(f"V3 stade non dicte : {t}")
    return list(dict.fromkeys(res))


def _contexte_ok(attendu, v: dict) -> bool:
    attendus = attendu if isinstance(attendu, list) else [attendu]
    return v.get("contexte") in attendus


def _pr_ok(attendu, v: dict) -> bool:
    attendus = attendu if isinstance(attendu, list) else [attendu]
    return v.get("prelevement") in attendus


def _norm_organe(o: str) -> str:
    return normaliser(o.replace("organe:", "")).replace(" ", "_")


def evaluer(cas: dict, v: dict) -> list[dict]:
    """Attentes ecrites d'avance, evaluees sur la vue normalisee. Retourne [{cat, lib, ok}]."""
    att: list[dict] = []

    def add(cat: str, lib: str, ok: bool) -> None:
        att.append({"cat": cat, "lib": lib, "ok": bool(ok)})

    if v.get("erreur"):
        if cas.get("ok_erreur"):
            add("robustesse", "refus propre de la dictee", True)
        else:
            add("robustesse", f"projet produit ({v['erreur']})", False)
        return att
    texte = normaliser(v["texte"])
    trous = [normaliser(t) for t in v["trous"]]
    sig = [normaliser(s["message"]) for s in v["signaux"] if s["gravite"] != "info"]
    if "organes_any" in cas:
        obt = {_norm_organe(o) for o in v["organes"]}
        add("contexte", f"organe parmi {cas['organes_any']}", any(_norm_organe(o) in obt for o in cas["organes_any"]))
    if "organes_min" in cas:
        add("contexte", f">= {cas['organes_min']} organes", len(v["organes"]) >= cas["organes_min"])
    if "prelevement" in cas:
        add("contexte", f"prelevement {cas['prelevement']}", _pr_ok(cas["prelevement"], v))
    if "contexte" in cas:
        add("contexte", f"contexte lesionnel {cas['contexte']}", _contexte_ok(cas["contexte"], v))
    for typ, motif in cas.get("alertes", []):
        if v["moteur"] == "nouveau":
            ok = any(s["gravite"] != "info" and (motif is None or re.search(motif, normaliser(s["message"]))) for s in v["signaux"])
        else:
            ok = any(re.search(motif, m) for m in sig) if motif else bool(sig)
        add("detection", f"alerte {typ} {motif or ''}", ok)
    for typ in cas.get("alertes_interdites", []):
        add("detection", f"aucune alerte {typ} (faux positif)", not any(s["categorie"] == typ and s["gravite"] != "info" for s in v["signaux"]))
    for rx in cas.get("requis", []):
        add("fidelite", f"requis /{rx}/", re.search(rx, texte))
    for rx in cas.get("interdits", []):
        add("fidelite", f"interdit /{rx}/", not re.search(rx, texte))
    for rx in cas.get("trous", []):
        add("detection", f"trou attendu /{rx}/", any(re.search(rx, t) for t in trous))
    for rx in cas.get("trous_interdits", []):
        add("detection", f"trou interdit /{rx}/", not any(re.search(rx, t) for t in trous))
    if "max_trous" in cas:
        add("detection", f"au plus {cas['max_trous']} trous ({len(trous)})", len(trous) <= cas["max_trous"])
    for rx in cas.get("corrections", []):
        corr = any(c["appliquee"] and re.search(rx, normaliser(c["corrige"])) for c in v.get("corrections", []))
        add("phonetique", f"correction STT /{rx}/", corr or re.search(rx, texte) or re.search(rx, normaliser(v.get("dictee_corrigee", ""))))
    if "dictee_corrigee_contient" in cas:
        rx = cas["dictee_corrigee_contient"]
        add("phonetique", f"dictee corrigee contient /{rx}/", re.search(rx, normaliser(v.get("dictee_corrigee", "")) + "\n" + texte))
    if cas.get("aucun_code"):
        add("codage", "aucun code propose", not [c for c in v["adicap"] if c["organe_code"] not in ("XX", "")])
    return att


def faux_trous(v: dict, dictee: str) -> list[str]:
    """Trou dont les mots distinctifs (>= 6 lettres) sont TOUS dictes : champ manquant a tort (meme regle, 2 moteurs)."""
    nd = normaliser(dictee)
    generiques = {"taille", "tumorale", "presence", "statut", "valeur", "nombre", "mesure", "type", "grade", "autre", "champ", "complet", "dimension"}
    res = []
    for t in v["trous"]:
        mots = [m for m in re.findall(r"[a-z]{6,}", normaliser(t)) if m not in generiques]
        if mots and all(re.search(rf"(?<![a-z]){re.escape(m[:6])}", nd) for m in mots):
            res.append(t)
    return res


_ORGANES_D3 = None


def _d3_attendu(cas: dict) -> str | None:
    global _ORGANES_D3
    if _ORGANES_D3 is None:
        from adicap import ORGANE_APP_TO_D3
        _ORGANES_D3 = ORGANE_APP_TO_D3
    if "organes_any" not in cas:
        return None
    for o in cas["organes_any"]:
        d3 = _ORGANES_D3.get(o.replace("organe:", ""))
        if d3:
            return d3
    return None


_PRELEV_ADICAP = {"biopsie": {"B"}, "piece_operatoire": {"O", "K"}, "cytologie": {"C", "F", "L", "G"}}


def mesure_adicap(cas: dict, v: dict) -> dict:
    """Codes ADICAP : produit (organe code), organe/prelevement conformes a l'attente, lesion proposee, lesion plausible."""
    d3 = _d3_attendu(cas)
    codes = [c for c in v.get("adicap", []) if c["organe_code"] not in ("XX", "")]
    res = {"produit": bool(codes), "organe_juste": None, "prelevement_juste": None, "lesion": False, "lesion_plausible": None}
    if not codes:
        return res
    if d3:
        res["organe_juste"] = any(c["organe_code"] == d3 for c in codes)
    if "prelevement" in cas and not isinstance(cas["prelevement"], list):
        res["prelevement_juste"] = any(c["prelevement_code"] in _PRELEV_ADICAP.get(cas["prelevement"], set()) for c in codes)
    lesions = [c for c in codes if c["lesion_code"] and set(c["lesion_code"]) != {"_"}]
    res["lesion"] = bool(lesions)
    if lesions:
        nd = normaliser(cas["dictee"])
        ok = True
        for c in lesions:
            mots = [m for m in re.findall(r"[a-z]{6,}", normaliser(c["libelle"].split(" - ")[-1])) if m not in {"carcinome"}]
            if mots and not any(re.search(rf"(?<![a-z]){re.escape(m[:6])}", nd) for m in mots):
                ok = False
        res["lesion_plausible"] = ok
    return res


def _a_chiffre(s: str) -> bool:
    return bool(re.search(r"\d", s))


def explicabilite(v: dict) -> dict:
    """Comptages objectifs d'explicabilite, definis identiquement quand c'est possible."""
    r: dict = {}
    if v["moteur"] == "nouveau":
        phrases = [e for e in v["elements"] if e["type"] in ("phrase", "liste")]
        avec = [e for e in phrases if any(s["kind"] == "dictee" and s.get("debut") is not None for s in e["sources"])]
        r["phrases"], r["phrases_sourcees"] = len(phrases), len(avec)
        r["refs_kb"] = sum(1 for e in v["elements"] for s in e["sources"] if s["kind"] == "kb") + \
            sum(1 for a in v["alertes"] for s in a["sources"] if s["kind"] in ("kb", "regle"))
        r["refs_kb_distinctes"] = len({s["libelle"] for e in v["elements"] for s in e["sources"] if s["kind"] == "kb"})
        al = [a for a in v["alertes"] if a["gravite"] != "info"]
        r["alertes"] = len(al)
        r["alertes_chiffrees"] = sum(1 for a in al if _a_chiffre(a["message"] + a["pourquoi"] + (a["calcul"] or "")))
        r["alertes_calcul"] = sum(1 for a in al if a["calcul"])
        r["alertes_action"] = sum(1 for a in al if a["action"])
        r["alertes_sourcees"] = sum(1 for a in al if a["sources"])
    else:
        n = v.get("n_assertions", 0)
        soum = v.get("college_soumissions", [])
        r["phrases"] = max(n, len(soum))
        r["phrases_sourcees"] = sum(1 for s in soum if s["empan"])
        r["refs_kb"] = 0
        r["refs_kb_distinctes"] = 0
        al = [s for s in v["signaux"] if s["gravite"] != "info"]
        r["alertes"] = len(al)
        r["alertes_chiffrees"] = sum(1 for s in al if _a_chiffre(s["message"]))
        r["alertes_calcul"] = 0
        r["alertes_action"] = 0
        r["alertes_sourcees"] = 0
        r["mentions_referentiel_texte"] = sum(1 for s in al if re.search(r"inca|oms|who|adicap|referentiel|recommandation", normaliser(s["message"])))
    return r


def a_relire(cas: dict, v: dict) -> dict:
    """Elements signales au praticien (hors trous) et part confirmee fautive.

    « Confirme » = un controle deterministe ou une attente ecrite d'avance le justifie ; sinon « non confirme »
    (ce qui ne veut pas dire faux : l'echantillon relu a la main est dans le rapport).
    """
    dictee = cas["dictee"]
    items: list[dict] = []
    motifs_attendus = [m for _, m in cas.get("alertes", []) if m] + [r for r in cas.get("interdits", [])]
    viol = violations_texte(v, dictee)
    if v["moteur"] == "nouveau":
        for e in v["elements"]:
            if e["type"] != "trou" and e.get("a_verifier"):
                conf = bool(viol and any(x in e["texte"] for x in re.findall(r"\d+", " ".join(viol)))) or \
                    any(re.search(rx, normaliser(e["texte"])) for rx in cas.get("interdits", []))
                items.append({"genre": "element", "texte": e["texte"][:120], "raison": e["a_verifier"], "confirme": conf})
        for a in v["alertes"]:
            if a["gravite"] == "info" or a["type"] == "manquant":
                continue
            msg = normaliser(a["message"] + " " + a["pourquoi"])
            exp = any(t == a["type"] and (m is None or re.search(m, msg)) for t, m in cas.get("alertes", []))
            items.append({"genre": "alerte:" + a["type"], "texte": a["message"][:120], "raison": a["pourquoi"][:120], "confirme": exp})
    else:
        for s in v["signaux"]:
            if s["categorie"] == "manquant" or s["gravite"] == "info":
                continue
            msg = normaliser(s["message"])
            exp = any(m is None or re.search(m, msg) for _, m in cas.get("alertes", []))
            items.append({"genre": s["src"], "texte": s["message"][:120], "raison": "", "confirme": exp})
        for s in v.get("college_soumissions", []):
            if s["comportement"] != "affirmer":
                items.append({"genre": "college_soumission", "texte": (s["assertion"] or "")[:120], "raison": s["motif"], "confirme": False,
                              "non_juge": True})
    return {"items": items, "n": len(items), "n_confirmes": sum(1 for i in items if i["confirme"]), "violations": viol}


def defauts_silencieux(cas: dict, v: dict, att: list[dict], ar: dict) -> dict:
    """Defauts reels (attente de fidelite/detection non tenue, ou violation deterministe) dans une sortie SANS signal."""
    echecs = [a for a in att if not a["ok"] and a["cat"] in ("fidelite", "detection", "phonetique")]
    defauts = bool(echecs or ar["violations"])
    signale = ar["n"] > 0 or bool(v["trous"])
    return {"defaut": defauts, "signale": signale, "silencieux": defauts and not signale}


def _pct(vals: list[float], q: float) -> float:
    if not vals:
        return 0.0
    s = sorted(vals)
    k = (len(s) - 1) * q
    f = int(k)
    c = min(f + 1, len(s) - 1)
    return s[f] + (s[c] - s[f]) * (k - f)


def analyser(brut: list[dict]) -> dict:
    cas_par_id = {c["id"]: c for c in charger_cas()}
    res: dict = {"moteurs": {}, "par_cas": defaultdict(dict)}
    for moteur in ("ancien", "nouveau"):
        vues = [v for v in brut if v["moteur"] == moteur and v.get("phase") == "lot"]
        if not vues:
            continue
        ok = [v for v in vues if not v["erreur"]]
        M: dict = {"n": len(vues), "erreurs": sum(1 for v in vues if v["erreur"] and not v["timeout"]),
                   "timeouts": sum(1 for v in vues if v["timeout"])}
        durees = [v["mur_ms"] for v in ok]
        M["p50_ms"], M["p95_ms"], M["max_ms"], M["moy_ms"] = _pct(durees, .5), _pct(durees, .95), max(durees or [0]), statistics.mean(durees or [0])
        M["plus_90s"] = sum(1 for d in durees if d > LATENCE_MAX_MS)
        isoles = [v for v in brut if v["moteur"] == moteur and v.get("phase") == "isole" and not v["erreur"]]
        M["isole_n"] = len(isoles)
        M["isole_p50_ms"] = _pct([v["mur_ms"] for v in isoles], .5)
        M["isole_p95_ms"] = _pct([v["mur_ms"] for v in isoles], .95)
        M["appels_moy"] = statistics.mean([v["appels"] for v in ok] or [0])
        M["appels_min"] = min([v["appels"] for v in ok] or [0])
        M["appels_max"] = max([v["appels"] for v in ok] or [0])
        M["echecs_appels"] = sum(v.get("echecs", 0) for v in vues)
        M["tok_in_moy"] = statistics.mean([v["tok_in"] for v in ok] or [0])
        M["tok_out_moy"] = statistics.mean([v["tok_out"] for v in ok] or [0])
        M["cout_moy_usd"] = (M["tok_in_moy"] * TARIFS["entree"] + M["tok_out_moy"] * TARIFS["sortie"]) / 1e6
        M["vides"] = sum(1 for v in ok if not v["texte"].strip() or len(v["texte"].split()) < 5)
        # attentes
        cats: dict[str, list[int]] = defaultdict(lambda: [0, 0])
        for v in vues:
            cas = cas_par_id[v["id"]]
            att = evaluer(cas, v)
            res["par_cas"][v["id"]][moteur] = {"attentes": att}
            for a in att:
                cats[a["cat"]][1] += 1
                cats[a["cat"]][0] += int(a["ok"])
        M["attentes"] = {k: tuple(x) for k, x in cats.items()}
        M["attentes_total"] = (sum(x[0] for x in cats.values()), sum(x[1] for x in cats.values()))
        # fidelite
        n_viol = n_chiffre = n_stade = 0
        mes_dictees = mes_retrouvees = mes_alterees = mes_sortie = 0
        neg_cons = neg_perdu = neg_inv = 0
        for v in ok:
            cas = cas_par_id[v["id"]]
            viol = violations_texte(v, cas["dictee"])
            res["par_cas"][v["id"]][moteur]["violations"] = viol
            n_viol += len(viol)
            n_chiffre += sum(1 for x in viol if x.startswith("V2"))
            n_stade += sum(1 for x in viol if x.startswith("V3"))
            md, ms = _mesures(cas["dictee"]), _mesures(v["texte"])
            mes_dictees += len(md)
            mes_retrouvees += len(md & ms)
            mes_sortie += len(ms)
            mes_alterees += len(ms - md)
            res["par_cas"][v["id"]][moteur]["mesures_alterees"] = sorted(ms - md)
            res["par_cas"][v["id"]][moteur]["mesures_perdues"] = sorted(md - ms)
            ng = _negations(cas["dictee"], v["texte"])
            res["par_cas"][v["id"]][moteur]["negations"] = ng
            neg_cons += len(ng["conserve"])
            neg_perdu += len(ng["perdu"])
            neg_inv += len(ng["inverse"])
        M.update(violations=n_viol, v2=n_chiffre, v3=n_stade, mes_dictees=mes_dictees, mes_retrouvees=mes_retrouvees,
                 mes_alterees=mes_alterees, mes_sortie=mes_sortie, neg_cons=neg_cons, neg_perdu=neg_perdu, neg_inv=neg_inv,
                 cas_avec_violation=sum(1 for v in ok if res["par_cas"][v["id"]][moteur]["violations"]))
        # faux trous
        ft = 0
        n_trous = 0
        for v in ok:
            f = faux_trous(v, cas_par_id[v["id"]]["dictee"])
            res["par_cas"][v["id"]][moteur]["faux_trous"] = f
            ft += len(f)
            n_trous += len(v["trous"])
        M["faux_trous"], M["trous_total"] = ft, n_trous
        # ADICAP
        ad = {"produit": 0, "organe_juste": [0, 0], "prelevement_juste": [0, 0], "lesion": 0, "lesion_plausible": [0, 0], "n": 0}
        for v in ok:
            a = mesure_adicap(cas_par_id[v["id"]], v)
            res["par_cas"][v["id"]][moteur]["adicap"] = a
            ad["n"] += 1
            ad["produit"] += a["produit"]
            ad["lesion"] += a["lesion"]
            for k in ("organe_juste", "prelevement_juste", "lesion_plausible"):
                if a[k] is not None:
                    ad[k][1] += 1
                    ad[k][0] += int(a[k])
        M["adicap"] = ad
        # explicabilite
        ex = defaultdict(int)
        for v in ok:
            e = explicabilite(v)
            res["par_cas"][v["id"]][moteur]["explic"] = e
            for k, x in e.items():
                ex[k] += x
        M["explic"] = dict(ex)
        # a relire
        ar_n = ar_c = 0
        sil = {"defaut": 0, "signale": 0, "silencieux": 0}
        n_soum = 0
        for v in ok:
            cas = cas_par_id[v["id"]]
            ar = a_relire(cas, v)
            res["par_cas"][v["id"]][moteur]["a_relire"] = ar
            non_juges = sum(1 for i in ar["items"] if i.get("non_juge"))
            n_soum += non_juges
            ar_n += ar["n"] - non_juges
            ar_c += ar["n_confirmes"]
            d = defauts_silencieux(cas, v, res["par_cas"][v["id"]][moteur]["attentes"], ar)
            res["par_cas"][v["id"]][moteur]["silence"] = d
            for k in sil:
                sil[k] += int(d[k])
        M["a_relire"], M["a_relire_confirmes"], M["soumissions_college"] = ar_n, ar_c, n_soum
        M["silence"] = sil
        M["corrections_appliquees"] = sum(1 for v in ok for c in v.get("corrections", []) if c["appliquee"])
        res["moteurs"][moteur] = M
    # domaines
    dom: dict = defaultdict(lambda: defaultdict(lambda: [0, 0]))
    for cid, d in res["par_cas"].items():
        for moteur, x in d.items():
            for a in x["attentes"]:
                dom[cas_par_id[cid]["domaine"]][moteur][1] += 1
                dom[cas_par_id[cid]["domaine"]][moteur][0] += int(a["ok"])
    res["domaines"] = {k: {m: tuple(vv) for m, vv in x.items()} for k, x in dom.items()}
    res["par_cas"] = dict(res["par_cas"])
    return res


def afficher(res: dict) -> None:
    for m, M in res["moteurs"].items():
        print(f"\n===== {m} =====")
        print(json.dumps(M, ensure_ascii=False, indent=1, default=str))
    print("\n===== domaines =====")
    for d, x in sorted(res["domaines"].items()):
        print(d, {m: f"{a}/{b}" for m, (a, b) in x.items()})


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--executer", action="store_true")
    ap.add_argument("--analyser", default="")
    ap.add_argument("--sortie", default="")
    ap.add_argument("--cas", default="")
    ap.add_argument("--moteurs", default="ancien,nouveau")
    ap.add_argument("--parallele", type=int, default=3)
    ap.add_argument("--isole", type=int, default=0, help="N dictees rejouees une par une (latence sans contention)")
    args = ap.parse_args()
    if args.executer:
        brut = await executer(args)
        if args.sortie:
            Path(args.sortie).write_text(json.dumps(brut, ensure_ascii=False, indent=1), encoding="utf-8")
            print("brut :", args.sortie)
        return 0
    if args.analyser:
        brut = [v for f in args.analyser.split(",") for v in json.loads(Path(f).read_text(encoding="utf-8"))]
        afficher(analyser(brut))
        return 0
    ap.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
