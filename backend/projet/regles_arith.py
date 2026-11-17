"""Controles arithmetiques deterministes, pilotes par les regles de la base de connaissances.

Chaque controle lit des valeurs DICTEES (ganglions, pN, pT, taille, pourcentages,
score de Nottingham, Gleason, Ki67), puis fait evaluer la condition declarative de la
regle KB par ``projet.kb.evaluer_condition``. Les seuils (tables pN/pT par organe) sont
dans la base (champ ``parametres`` de la regle), jamais dans ce code.

Un controle est rendu qu'il declenche ou non : l'orchestrateur en fait une alerte
quand il declenche, et une preuve « ok » affichee sous les elements concernes sinon.
Une valeur absente ou ambigue ne produit AUCUN controle (zero faux positif).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from projet.kb import evaluer_condition
from projet.mesures import chiffrer, extraire_mesures, formater_valeur
from projet.referentiel import Referentiel
from projet.schemas import SourceRef
from text_utils import normaliser


@dataclass(slots=True)
class Controle:
    regle_id: str
    code: str                      # affiche : « C4 », « A3 »...
    titre: str
    declenche: bool
    calcul: str                    # « 2 envahis ≤ 12 examinés »
    detail: str                    # une phrase factuelle
    gravite: str                   # bloquant | attention | info
    source: SourceRef
    ancres: list[str] = field(default_factory=list)   # fragments (normalises) qui rattachent le controle aux elements
    suggestion: str | None = None
    action: str = ""
    alerter: bool = True           # False : l'alerte existe deja ailleurs (C4), seule la preuve est produite


def _f(v: float | int) -> str:
    return formater_valeur(float(v))


def _source(ref: Referentiel, regle: dict, libelle_extra: str | None = None) -> SourceRef:
    prov = regle.get("prov") or {}
    return ref.source_ref(prov.get("source_id"), localisation=libelle_extra or prov.get("localisation"),
                          fiabilite=prov.get("fiabilite"))


def _source_organe(ref: Referentiel, regle: dict, organe_id: str) -> SourceRef:
    """Source de la table pN/pT : RCPath (verifie) pour le sein, connaissance du domaine a valider ailleurs."""
    if organe_id == "organe:sein":
        return ref.source_ref("src:uicc_tnm8_rcpath", localisation="sein, seuils TNM 8 (RCPath, appendice D)", fiabilite="A")
    nom = organe_id.split(":", 1)[1].replace("_", "-")
    return ref.source_ref("src:uicc_tnm8_rcpath", localisation=f"{nom} : seuils TNM 8, connaissance du domaine, à valider par la pathologiste référente",
                          fiabilite="C")


def _code(regle_id: str) -> str:
    return regle_id.split(":", 1)[1].split("_", 1)[0].upper()


# ---------------------------------------------------------------------------
# Extraction des valeurs dictees (texte chiffre et normalise)
# ---------------------------------------------------------------------------

_EXAMINES = re.compile(r"(\d+)\s+ganglions?\s+(?:lymphatiques?\s+)?(?:examin|analys|prelev|isol|identifi|retrouv|dont\b)")
_ENVAHIS = re.compile(
    r"(\d+)\s+(?:ganglions?\s+)?(?:sont\s+)?(?:metastatiques?|envahis?|positifs?|atteints?|metastases?)")
_PN = re.compile(r"(?<![a-z0-9])(?:yp|p)?n(0|1mi|1[a-c]?|2[a-b]?|3[a-b]?)(?![a-z0-9])")
_PT = re.compile(r"(?<![a-z0-9])(?:yp|p)?t(1mi|1[a-c]?|2[a-b]?|3|4[a-e]?)(?![a-z0-9])")
_PCT = re.compile(r"(\d+(?:[.,]\d+)?)\s*(?:%|pour ?cent)")
_MOTS_COMPOSANTES = re.compile(r"pattern|composante|contingent|lepidique|acineu|papillaire|solide|cribriforme|"
                               r"micropapillaire|mucineu|sous-type|architecture")
_SBR_CONTEXTE = re.compile(r"sbr|nottingham|elston")
_ROMAIN = {"i": 1, "ii": 2, "iii": 3, "1": 1, "2": 2, "3": 3}


def _un_seul(valeurs: list[int]) -> int | None:
    uniques = set(valeurs)
    return uniques.pop() if len(uniques) == 1 else None


def _evaluer(ref: Referentiel, regle_id: str, variables: dict) -> tuple[dict | None, bool]:
    regle = ref._kb_appel("regle", regle_id, defaut=None)
    if not regle:
        return None, False
    return regle, evaluer_condition(regle["condition"], variables)


def _gravite(regle: dict) -> str:
    g = str(regle.get("severite") or "attention")
    return g if g in ("bloquant", "attention", "info") else "attention"


def _ganglions(norm: str, ref: Referentiel) -> list[Controle]:
    examines = [int(m.group(1)) for m in _EXAMINES.finditer(norm)]
    envahis = [int(m.group(1)) for m in _ENVAHIS.finditer(norm)]
    n_ex, n_env = _un_seul(examines), _un_seul(envahis)
    if n_ex is None or n_env is None:
        return []
    regle, decl = _evaluer(ref, "regle:c4_ganglions_envahis_inferieur_examines",
                           {"ganglions_envahis": n_env, "ganglions_examines": n_ex})
    if regle is None:
        return []
    op = ">" if decl else "≤"
    return [Controle(
        regle_id=regle["id"], code="C4", titre="Ganglions envahis ≤ examinés", declenche=decl,
        calcul=f"{n_env} envahis {op} {n_ex} examinés",
        detail=(f"{n_env} ganglions envahis pour {n_ex} examinés : impossible." if decl
                else f"{n_env} ganglions envahis pour {n_ex} examinés : cohérent."),
        gravite=_gravite(regle), source=_source(ref, regle), ancres=[f"{n_ex} ganglion", f"{n_env} metastatique",
                                                                    f"{n_env} envahi", f"{n_env} ganglion"],
        action="Vérifier les deux nombres dans la dictée", alerter=False)]


def _pn(norm: str, ref: Referentiel, organe_id: str | None) -> list[Controle]:
    if not organe_id:
        return []
    m = _PN.search(norm)
    n_env = _un_seul([int(x.group(1)) for x in _ENVAHIS.finditer(norm)])
    if not m or n_env is None:
        return []
    regle = ref._kb_appel("regle", "regle:a3_pn_ganglions_envahis", defaut=None)
    if not regle:
        return []
    cat = "N" + m.group(1)
    table = ((regle.get("parametres") or {}).get("organes") or {}).get(organe_id) or {}
    bornes = table.get(cat)
    if bornes is None:
        return []
    mini, maxi = bornes
    variables: dict = {"ganglions_envahis": n_env, "pn_min": mini, "pn_max": maxi}
    decl = evaluer_condition(regle["condition"], variables)
    intervalle = f"{mini}" + (f"–{maxi}" if maxi is not None and maxi != mini else (" ou plus" if maxi is None else ""))
    return [Controle(
        regle_id=regle["id"], code="A3", titre=f"p{cat} et ganglions envahis", declenche=decl,
        calcul=f"p{cat} = {intervalle} ganglion(s) envahi(s) ; dicté : {n_env}",
        detail=(f"p{cat} annoncé avec {n_env} ganglion(s) envahi(s) : hors de l'intervalle {intervalle}." if decl
                else f"p{cat} compatible avec {n_env} ganglion(s) envahi(s) (attendu : {intervalle})."),
        gravite=_gravite(regle), source=_source_organe(ref, regle, organe_id),
        ancres=[m.group(0), f"{n_env} metastatique", f"{n_env} envahi"],
        suggestion=f"Vérifier la catégorie p{cat} ou le nombre de ganglions envahis",
        action="Confirmer la catégorie pN ou le nombre de ganglions envahis")]


def _pt(norm: str, texte_chiffre: str, ref: Referentiel, organe_id: str | None) -> list[Controle]:
    if not organe_id:
        return []
    m = _PT.search(norm)
    tailles = [max(mm.valeurs_mm) for mm in extraire_mesures(texte_chiffre) if mm.objet == "tumeur" and mm.valeurs_mm]
    if not m or not tailles:
        return []
    regle = ref._kb_appel("regle", "regle:a4_pt_taille", defaut=None)
    if not regle:
        return []
    cat = "T" + m.group(1)
    bornes = (((regle.get("parametres") or {}).get("organes") or {}).get(organe_id) or {}).get(cat)
    if bornes is None:
        return []
    taille = max(tailles)
    mini, maxi = bornes
    variables = {"taille_mm": taille, "pt_min_mm": mini, "pt_max_mm": maxi}
    decl = evaluer_condition(regle["condition"], variables)
    if mini is not None and maxi is not None:
        intervalle = f"> {_f(mini)} et ≤ {_f(maxi)} mm"
    elif maxi is not None:
        intervalle = f"≤ {_f(maxi)} mm"
    else:
        intervalle = f"> {_f(mini)} mm"
    return [Controle(
        regle_id=regle["id"], code="A4", titre=f"p{cat} et taille tumorale", declenche=decl,
        calcul=f"{_f(taille)} mm ; p{cat} attend {intervalle}",
        detail=(f"Tumeur de {_f(taille)} mm : hors de la plage de p{cat} ({intervalle})." if decl
                else f"Tumeur de {_f(taille)} mm : compatible avec p{cat} ({intervalle})."),
        gravite=_gravite(regle), source=_source_organe(ref, regle, organe_id),
        ancres=[m.group(0)] + [normaliser(mm.texte) for mm in extraire_mesures(texte_chiffre) if mm.objet == "tumeur"],
        suggestion=f"Vérifier la catégorie p{cat} ou la taille", action="Confirmer la catégorie pT ou la taille tumorale")]


def _pourcentages(norm: str, ref: Referentiel) -> list[Controle]:
    res: list[Controle] = []
    valeurs = [float(x.replace(",", ".")) for x in _PCT.findall(norm)]
    if valeurs:
        regle, decl = _evaluer(ref, "regle:a1_pourcentage_max_100", {"pct_max": max(valeurs)})
        if regle is not None:
            res.append(Controle(
                regle_id=regle["id"], code="A1", titre="Pourcentages ≤ 100 %", declenche=decl,
                calcul=f"max {_f(max(valeurs))} % {'>' if decl else '≤'} 100 %",
                detail=(f"Un pourcentage de {_f(max(valeurs))} % dépasse 100 %." if decl
                        else f"Tous les pourcentages dictés ({', '.join(_f(v) for v in valeurs)}) sont ≤ 100 %."),
                gravite=_gravite(regle), source=_source(ref, regle),
                ancres=[f"{_f(max(valeurs))} %", f"{_f(max(valeurs))}%", f"{_f(max(valeurs))} pour cent"],
                suggestion="Vérifier le pourcentage dicté", action="Corriger le pourcentage"))
    for phrase in re.split(r"[.;\n]", norm):
        vals = [float(x.replace(",", ".")) for x in _PCT.findall(phrase)]
        if len(vals) >= 2 and _MOTS_COMPOSANTES.search(phrase):
            regle, decl = _evaluer(ref, "regle:a2_composantes_somme_100", {"composantes_pct": vals})
            if regle is None:
                continue
            total = sum(vals)
            res.append(Controle(
                regle_id=regle["id"], code="A2", titre="Somme des composantes ≤ 100 %", declenche=decl,
                calcul=" + ".join(_f(v) for v in vals) + f" = {_f(total)} % {'> 100 %' if decl else '≤ 100 %'}",
                detail=(f"Les composantes totalisent {_f(total)} %." if decl
                        else f"Les composantes totalisent {_f(total)} % : cohérent."),
                gravite=_gravite(regle), source=_source(ref, regle), ancres=[f"{_f(v)} %" for v in vals] + [f"{_f(v)}%" for v in vals],
                suggestion="Vérifier les pourcentages de chaque composante", action="Corriger un des pourcentages"))
    return res


def _sbr(norm: str, ref: Referentiel) -> list[Controle]:
    for phrase in re.split(r"[.;\n]", norm):
        if not _SBR_CONTEXTE.search(phrase):
            continue
        g = re.search(r"(?:grade|sbr|nottingham|elston)[^.;\n]{0,25}?\b(iii|ii|i|[123])\b(?!\s*[+/])", phrase)
        compo = re.search(r"\b([123])\s*\+\s*([123])\s*\+\s*([123])\b", phrase)
        t = re.search(r"score[^.;\n]{0,25}?\b([3-9])\b(?!\s*[+])", phrase)
        total = (int(compo.group(1)) + int(compo.group(2)) + int(compo.group(3))) if compo else (int(t.group(1)) if t else None)
        if not g or total is None:
            continue
        grade = _ROMAIN[g.group(1)]
        regle, decl = _evaluer(ref, "regle:a5_grade_sbr_score", {"sbr_grade": grade, "sbr_total": total})
        if regle is None:
            continue
        attendu = "I" if total <= 5 else "II" if total <= 7 else "III"
        return [Controle(
            regle_id=regle["id"], code="A5", titre="Grade SBR et score de Nottingham", declenche=decl,
            calcul=f"score {total} → grade {attendu} ; dicté : grade {'I' * grade}",
            detail=(f"Score {total} correspond au grade {attendu}, pas au grade {'I' * grade}." if decl
                    else f"Score {total} correspond bien au grade {attendu}."),
            gravite=_gravite(regle), source=_source(ref, regle), ancres=["sbr", "nottingham", "elston", "grade"],
            suggestion=f"Vérifier le grade (le score {total} donne le grade {attendu})",
            action="Confirmer le grade ou le score")]
    return []


def _gleason(norm: str, ref: Referentiel) -> list[Controle]:
    res: list[Controle] = []
    m = re.search(r"gleason[^.;\n]{0,25}?(\d)\s*(?:\+|plus)\s*(\d)(?:\s*(?:=|soit)\s*(\d{1,2}))?", norm)
    if not m:
        return res
    p, s = int(m.group(1)), int(m.group(2))
    if m.group(3):
        total = int(m.group(3))
        regle, decl = _evaluer(ref, "regle:u6_gleason_somme",
                               {"gleason_primaire": p, "gleason_secondaire": s, "gleason_total": total})
        if regle is not None:
            res.append(Controle(
                regle_id=regle["id"], code="U6", titre="Gleason : somme des grades", declenche=decl,
                calcul=f"{p} + {s} = {p + s} ; dicté : {total}",
                detail=(f"{p}+{s} fait {p + s}, pas {total}." if decl else f"{p}+{s} = {p + s} : conforme au total dicté."),
                gravite=_gravite(regle), source=_source(ref, regle), ancres=["gleason"],
                suggestion=f"Total attendu : {p + s}", action="Confirmer le total ou les grades"))
    i = re.search(r"(?:isup|grade group|groupe)[^.;\n]{0,10}?\b([1-5])\b", norm)
    if i:
        isup = int(i.group(1))
        regle, decl = _evaluer(ref, "regle:u7_gleason_isup", {"gleason_primaire": p, "gleason_secondaire": s, "isup": isup})
        if regle is not None:
            total = p + s
            attendu = 1 if total <= 6 else (2 if (p, s) == (3, 4) else 3 if (p, s) == (4, 3) else 4 if total == 8 else 5)
            res.append(Controle(
                regle_id=regle["id"], code="U7", titre="Gleason et groupe ISUP", declenche=decl,
                calcul=f"Gleason {p}+{s} → ISUP {attendu} ; dicté : {isup}",
                detail=(f"Gleason {p}+{s} correspond à l'ISUP {attendu}, pas {isup}." if decl
                        else f"Gleason {p}+{s} correspond bien à l'ISUP {attendu}."),
                gravite=_gravite(regle), source=_source(ref, regle), ancres=["isup", "gleason", "grade group"],
                suggestion=f"Groupe ISUP attendu : {attendu}", action="Confirmer le groupe ISUP ou le score"))
    return res


def _ki67(norm: str, ref: Referentiel) -> list[Controle]:
    m = re.search(r"ki ?-?67[^.;\n%]{0,25}?(\d+(?:[.,]\d+)?)\s*(?:%|pour ?cent)", norm)
    if not m:
        return []
    v = float(m.group(1).replace(",", "."))
    regle, decl = _evaluer(ref, "regle:u4_ki67_hors_0_100", {"ki67_pct": v})
    if regle is None:
        return []
    return [Controle(
        regle_id=regle["id"], code="U4", titre="Ki67 entre 0 et 100 %", declenche=decl,
        calcul=f"{_f(v)} % {'hors de' if decl else 'dans'} 0–100 %",
        detail=(f"Ki67 de {_f(v)} % impossible." if decl else f"Ki67 de {_f(v)} % dans la plage 0–100 %."),
        gravite=_gravite(regle), source=_source(ref, regle), ancres=["ki67", "ki 67"],
        suggestion="Vérifier la valeur de Ki67", action="Corriger la valeur de Ki67")]


def controles(texte: str, ref: Referentiel, organe_id: str | None) -> list[Controle]:
    """Tous les controles arithmetiques applicables au texte (dictee corrigee en general)."""
    chiffre = chiffrer(texte)
    norm = normaliser(chiffre)
    res: list[Controle] = []
    for fn in (lambda: _ganglions(norm, ref), lambda: _pn(norm, ref, organe_id),
               lambda: _pt(norm, chiffre, ref, organe_id), lambda: _pourcentages(norm, ref),
               lambda: _sbr(norm, ref), lambda: _gleason(norm, ref), lambda: _ki67(norm, ref)):
        try:
            res.extend(fn())
        except Exception:  # noqa: BLE001 - un controle fautif est ignore, jamais bloquant
            continue
    return res


def concerne(controle: Controle, texte_element: str) -> bool:
    """Le controle porte-t-il sur cet element (un de ses fragments y figure) ?"""
    norm = normaliser(chiffrer(texte_element))
    return any(a and normaliser(a) in norm for a in controle.ancres)


# ---------------------------------------------------------------------------
# Format IHC : « marqueur : resultat »
# ---------------------------------------------------------------------------

_RESULTAT_IHC = (r"(?:(?:faiblement|fortement|moderement|focalement|diffusement)\s+)?(?:positifs?|positives?|negatifs?|negatives?|"
                 r"exprime[e]?s?|non exprime[e]?s?|perte d'expression|expression conservee|conservee|heterogene|focal[e]?|"
                 r"diffus[e]?|forte?|faible|intense|moderee?|douteu[xs]e?|\d+(?:[.,]\d+)?\s*%|[0-3]\s*\+)")
_PAIRE_IHC = re.compile(rf"\s*(?P<marqueur>[^\s:;]+(?:\s+[^\s:;]+){{0,3}}?)\s*:\s*(?P<resultat>{_RESULTAT_IHC}"
                        rf"(?:\s*(?:,|et)?\s*{_RESULTAT_IHC})*)", re.IGNORECASE)


def eclater_ihc(texte: str) -> list[str]:
    """« TTF1 : positif Cytokératine 7 : positif P40 : négatif » -> un item « marqueur : résultat » par marqueur.

    Decoupe d'abord par lignes ou « ; », puis, dans une ligne, par paires « marqueur : resultat »
    reconnues de bout en bout. Une ligne non reconnue est gardee telle quelle.
    """
    items: list[str] = []
    for ligne in re.split(r"[\n;]+", texte):
        ligne = ligne.strip(" -•\t")
        if not ligne:
            continue
        norm = normaliser(ligne)
        pos, paires = 0, []
        while pos < len(norm):
            m = _PAIRE_IHC.match(norm, pos)
            if not m:
                break
            paires.append((m.start("marqueur"), m.end()))
            pos = m.end()
        # offsets de la forme normalisee : valables seulement si la normalisation conserve les longueurs
        if len(norm) == len(ligne) and len(paires) >= 2 and pos >= len(norm.rstrip()):
            items.extend(ligne[d:f].strip(" ,") for d, f in paires)
        else:
            items.append(ligne)
    return items


def ihc_non_conformes(lignes: list[str]) -> list[str]:
    """Lignes d'IHC qui ne suivent pas « marqueur : resultat »."""
    return [l for l in lignes if not _PAIRE_IHC.fullmatch(normaliser(l).strip(" ,."))]
