"""Agent codeur : ADICAP (deterministe, statut certain/partiel) + SNOMED CT (suggestion).

Regles :
- l'ADICAP est recompose par ``adicap.py`` qui DIFFERE la lesion (« ____ ») des
  que la correspondance n'est pas nette : jamais de lesion inventee ;
- le codeur ne lit que le contenu AFFIRME du projet final (les trous et les
  elements retires n'existent plus a ce stade), negations masquees ;
- SNOMED CT reste une « suggestion » tant que la base ne declare pas la table
  validee contre une edition officielle.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from adicap import suggerer_adicap
from projet.referentiel import OrganeDetecte, Referentiel
from projet.schemas import Alerte, Code, SourceRef
from projet.textes import extrait_court, localiser_exacte
from snomed import suggerer_snomed


@dataclass(slots=True)
class ResultatCodage:
    codes: list[Code] = field(default_factory=list)
    alertes: list[Alerte] = field(default_factory=list)
    details: list[str] = field(default_factory=list)


def _source_dictee(terme: str, dictee: str) -> list[SourceRef]:
    for mot in terme.replace("(", " ").replace(")", " ").split():
        if len(mot) < 6:
            continue
        loc = localiser_exacte(mot, dictee)
        if loc:
            return [SourceRef(kind="dictee", ref="dictee", libelle="Dictée", extrait=extrait_court(loc.extrait),
                              debut=loc.debut, fin=loc.fin)]
    return []


def _snomed_valide(ref: Referentiel) -> bool:
    manifeste = ref._kb_appel("manifeste", defaut={}) or {}
    snomed = manifeste.get("snomed") if isinstance(manifeste, dict) else None
    return bool(isinstance(snomed, dict) and snomed.get("valide"))


#: Une lesion par clause : on code chaque lesion AFFIRMEE de la conclusion, pas seulement la premiere.
_COUPURE_CLAUSE = re.compile(r"[.;\n]+|\s+(?:et|avec|associ\w+|sur fond de|ainsi que)\s+|\s*\+\s*")
MAX_LESIONS_PAR_ORGANE = 3


def _clauses_diagnostic(texte: str) -> tuple[str, list[str]]:
    """(texte qui precede la conclusion, clauses de la conclusion)."""
    bas = texte.lower()
    idx = bas.rfind("conclusion")
    base, conclusion = (texte[:idx], texte[idx + len("conclusion"):]) if idx != -1 else ("", texte)
    clauses = [re.sub(r"^\W*(?:\d{1,2}\s*[).:-])?\W*", "", c).strip() for c in _COUPURE_CLAUSE.split(conclusion)]
    return base, [c for c in clauses if len(c.split()) >= 2]


def _adicap_par_lesion(texte: str, organe_id: str, principal: dict[str, str]) -> list[dict[str, str]]:
    """Codes ADICAP certains, un par lesion distincte de la conclusion (principal compris)."""
    base, clauses = _clauses_diagnostic(texte)
    trouves: list[dict[str, str]] = []
    vus: set[str] = set()
    candidats = ([principal] if principal.get("confidence") == "haute" else [])
    if len(clauses) > 1:
        for c in clauses:
            try:
                a = suggerer_adicap(f"{base}\nConclusion : {c}", organe_id)
            except Exception:  # noqa: BLE001 - un echec de clause n'invalide pas les autres
                continue
            if a.get("confidence") == "haute":
                candidats.append(a)
    for a in candidats:
        if a["code"] not in vus and a["lesion_code"] not in {x["lesion_code"] for x in trouves}:
            vus.add(a["code"])
            trouves.append(a)
    return trouves[:MAX_LESIONS_PAR_ORGANE]


def coder(texte_projet: str, dictee: str, organes: list[OrganeDetecte], ref: Referentiel) -> ResultatCodage:
    """Codes ADICAP (un par organe, 3 max) et SNOMED CT (topographie + morphologie)."""
    res = ResultatCodage()
    if not texte_projet.strip():
        return res
    src_adicap = ref.source_ref("src:adicap_2024_10") if ref.source("src:adicap_2024_10") \
        else ref.source_ref("src:adicap_embarque")
    cibles = organes[:3] or [None]
    for organe in cibles:
        try:
            a = suggerer_adicap(texte_projet, organe.id_historique if organe else "")
        except Exception as exc:  # noqa: BLE001 - le codage ne bloque jamais le projet
            res.details.append(f"ADICAP indisponible : {type(exc).__name__}")
            continue
        if a.get("organe_code") == "XX":
            res.alertes.append(Alerte(
                id=f"k{len(res.alertes) + 1}", type="codage", gravite="info",
                message="ADICAP non proposé : organe sans code D3 certain (aucun code inventé).",
                confiance=1.0, sources=[src_adicap], agent="Codeur",
                pourquoi="Le thésaurus ADICAP n'a pas de code organe certain pour cet organe ; aucun code n'est inventé.",
                action="Coder cet examen à la main"))
            continue
        lesions = _adicap_par_lesion(texte_projet, organe.id_historique if organe else "", a) or [a]
        for a in lesions:
            certain = a.get("confidence") == "haute"
            explication = (
                f"Prélèvement {a['prelevement']} ({a['prelevement_code']}), technique {a['technique']} "
                f"({a['technique_code']}), organe {a['organe']} ({a['organe_code']}), lésion {a['lesion']} "
                f"({a['lesion_code']})."
            )
            if not certain:
                explication += " Code lésionnel différé : pas de correspondance certaine, à compléter."
            if any(c.systeme == "ADICAP" and c.code == a["code"] for c in res.codes):
                continue  # meme code pour deux organes cites : propose une seule fois
            res.codes.append(Code(
                systeme="ADICAP", code=a["code"], libelle=f"{a['organe']} - {a['lesion']}",
                statut="certain" if certain else "partiel", confiance=0.85 if certain else 0.6,
                sources=[src_adicap, *(_source_dictee(a["lesion"], dictee) if certain else [])],
                explication=explication,
            ))
            res.details.append(f"ADICAP {a['code']} ({'certain' if certain else 'partiel'})")
    # SNOMED CT
    try:
        s = suggerer_snomed(texte_projet, organes[0].id_historique if organes else "")
    except Exception as exc:  # noqa: BLE001
        res.details.append(f"SNOMED indisponible : {type(exc).__name__}")
        return res
    valide = _snomed_valide(ref)
    src_snomed = ref.source_ref("src:snomed_py_historique")
    mention = "" if valide else " Suggestion non validée contre une édition officielle SNOMED CT."
    for cle, libelle_axe in (("topography", "topographie"), ("morphology", "morphologie")):
        c = s.get(cle)
        if not isinstance(c, dict) or not c.get("code"):
            continue
        sources = [src_snomed]
        if cle == "morphology":
            sources += _source_dictee(str(c.get("display", "")), dictee)
        res.codes.append(Code(
            systeme="SNOMED_CT", code=str(c["code"]), libelle=str(c.get("display", "")),
            statut="suggestion", confiance=0.6 if valide else 0.45, sources=sources,
            explication=f"SNOMED CT ({libelle_axe}) depuis le contenu affirmé du projet.{mention}",
        ))
        res.details.append(f"SNOMED {libelle_axe} {c['code']}")
    return res
