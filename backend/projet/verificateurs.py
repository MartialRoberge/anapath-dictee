"""Verificateurs deterministes (unites, coherence, completude, securite).

Ils tournent EN PARALLELE apres la redaction (``asyncio.gather`` dans
l'orchestrateur, avec le relecteur LLM). Aucun ne modifie le brouillon : chacun
rend une ``Decision`` (alertes, retraits, reparations, trous) que l'orchestrateur
applique ensuite dans un ordre fixe. Cela rend chaque etape testable seule et
la trace lisible (« qui a retire quoi, pourquoi »).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from models import DonneeManquante
from negation import est_nie, mask_negations
from projet.extracteur import Extraction
from projet.mesures import Mesure, chiffrer, decrire_mesure_mm, extraire_mesures, formater_valeur
from projet.referentiel import ChampAttendu, OrganeDetecte, Plage, Referentiel
from projet.rendu import elements_touches, rendu_controle
from projet.schemas import Alerte, Element, Section, SourceRef
from projet.textes import contient_terme, extrait_court, localiser_exacte
from reports.coherence_document import (
    _lateralite_unique,
    regle_c4_envahis_inferieur_examines,
    verifier_coherence_document,
)
from reports.guardrails import filter_present_alertes
from reports.numbers import chiffres_non_dictes, source_number_set
from text_utils import normaliser


@dataclass(slots=True)
class Decision:
    """Sortie d'un verificateur : rien n'est applique ici."""

    alertes: list[Alerte] = field(default_factory=list)
    retraits: dict[str, str] = field(default_factory=dict)        # element_id -> raison
    reparations: dict[str, str] = field(default_factory=dict)     # element_id -> nouveau texte
    trous_a_ajouter: list[ChampAttendu] = field(default_factory=list)
    trous_a_retirer: dict[str, str] = field(default_factory=dict)  # element_id -> raison
    #: passages dictes repris par aucun element : (debut, fin, texte) dans la dictee corrigee
    omissions: list[tuple[int, int, str]] = field(default_factory=list)
    details: list[str] = field(default_factory=list)


class _Ids:
    """Generateur d'identifiants d'alertes stables par prefixe."""

    def __init__(self, prefixe: str) -> None:
        self.p, self.n = prefixe, 0

    def __call__(self) -> str:
        self.n += 1
        return f"{self.p}{self.n}"


def _src_dictee(debut: int, fin: int, texte: str) -> SourceRef:
    return SourceRef(kind="dictee", ref="dictee", libelle="Dictée", extrait=extrait_court(texte[debut:fin]),
                     debut=debut, fin=fin)


def _src_regle(ref: str, libelle: str, fiabilite: str = "B") -> SourceRef:
    return SourceRef(kind="regle", ref=ref, libelle=libelle, fiabilite=fiabilite)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# 1. Unites (mm / cm)
# ---------------------------------------------------------------------------

_LIBELLE_PRELEVEMENT = {"biopsie": "une biopsie", "cytologie": "une cytologie",
                        "piece_operatoire": "une pièce opératoire", "curage": "un curage"}


def _elements_contenant(elements: list[Element], m: Mesure) -> list[str]:
    ids = []
    for e in elements:
        for s in e.sources:
            if s.kind == "dictee" and s.debut is not None and s.fin is not None and s.debut < m.fin and s.fin > m.debut:
                ids.append(e.id)
                break
    return ids


_ARTICLE = {"biopsie": "une", "carotte": "une", "tumeur": "une", "pièce": "une", "marge": "une", "cytologie": "une",
            "fragment": "un", "polype": "un", "ganglion": "un"}


def avec_article(contexte: str) -> str:
    mot = contexte.split()[0].lower() if contexte else ""
    art = _ARTICLE.get(mot)
    return f"{art} {contexte}" if art else contexte


def calcul_plage(m: Mesure, plage: Plage) -> str:
    """Calcul lisible d'une mesure contre sa plage : « 20–40 mm > 5 mm (max biopsie bronchique) »."""
    contexte = plage.contexte or plage.libelle
    valeur = decrire_mesure_mm(m)
    if m.max_mm > plage.max_mm:
        return f"{valeur} > {formater_valeur(plage.max_mm)} mm (max {contexte})"
    if m.max_mm < plage.min_mm:
        return f"{valeur} < {formater_valeur(plage.min_mm)} mm (min {contexte})"
    return f"{valeur} dans {formater_valeur(plage.min_mm)}–{formater_valeur(plage.max_mm)} mm ({contexte})"


def _valeurs_dictees(m: Mesure) -> str:
    """Valeurs de la mesure telles que dictees : « 2 a 4 » (intervalle) ou « 25 x 18 » (axes)."""
    sep = " à " if m.intervalle else " x "
    return sep.join(formater_valeur(v) for v in m.valeurs)


def verifier_unites(dictee: str, elements: list[Element], ref: Referentiel, organe: OrganeDetecte | None,
                    prelevement: str | None) -> Decision:
    """Mesures hors plage plausible (mm pris pour cm et inversement) + conversions dans le projet."""
    d = Decision()
    nid = _Ids("u")
    mesures = extraire_mesures(dictee)
    d.details.append(f"{len(mesures)} mesure(s) repérée(s) dans la dictée")
    for m in mesures:
        categorie = m.objet
        if categorie is None and prelevement == "biopsie":
            categorie = "fragment"  # sur biopsie, une mesure sans objet decrit le prelevement
        if categorie is None:
            continue
        plage = ref.plage(organe.id if organe else None, categorie, prelevement)
        if plage is None:
            continue
        val = m.max_mm
        if plage.min_mm <= val <= plage.max_mm:
            continue
        suggestion = None
        if m.unite == "cm" and plage.min_mm <= val / 10 <= plage.max_mm:
            suggestion = "mm"
        elif m.unite == "mm" and plage.min_mm <= val * 10 <= plage.max_mm:
            suggestion = "cm"
        valeurs = _valeurs_dictees(m)
        contexte = _LIBELLE_PRELEVEMENT.get(prelevement or "", "ce prélèvement")
        objet = m.objet_mot or categorie
        message = (f"« {m.texte} » pour {objet} sur {contexte} : valeur hors de la plage plausible "
                   f"({formater_valeur(plage.min_mm)} à {formater_valeur(plage.max_mm)} mm).")
        sugg = None
        if suggestion:
            message += f" Unité probablement mal transcrite : {valeurs} {suggestion} ?"
            sugg = f"{valeurs} {suggestion}"
        d.alertes.append(Alerte(
            id=nid(), type="unite", gravite="attention", message=message,
            element_ids=_elements_contenant(elements, m), suggestion=sugg,
            confiance=0.8 if suggestion else 0.6,
            sources=[_src_dictee(m.debut, m.fin, dictee), plage.source], agent="Vérificateur d'unités",
            pourquoi=(f"« {m.texte} » sort de la plage habituelle pour {avec_article(plage.contexte or objet)} "
                      f"({formater_valeur(plage.min_mm)} à {formater_valeur(plage.max_mm)} mm) : "
                      "une confusion entre mm et cm est possible."),
            calcul=calcul_plage(m, plage),
            action=(f"Confirmer l'unité dictée, ou corriger en {sugg}" if sugg else "Confirmer la mesure dictée"),
        ))
    # Dimensions dictees SANS unite (« lobe 20 par 19 par 9 ») : jamais completees en silence.
    for m in _DIMENSIONS_SANS_UNITE.finditer(dictee):
        if any(mm.debut <= m.start() < mm.fin for mm in mesures):
            continue
        d.alertes.append(Alerte(
            id=nid(), type="unite", gravite="attention",
            message=f"Dimensions dictées sans unité : « {m.group(0).strip()} ». L'unité (mm ou cm) est à préciser.",
            suggestion="Préciser l'unité", confiance=0.9,
            sources=[_src_dictee(m.start(), m.end(), dictee)], agent="Vérificateur d'unités",
            pourquoi="Aucune unité n'a été dictée pour ces dimensions ; MARC n'en suppose jamais.",
            calcul=None, action="Préciser mm ou cm dans la dictée"))
    # Conversions ou changements d'unite introduits par la redaction : interdits.
    for e in elements:
        if e.type == "trou":
            continue
        texte, reparees, _ = reparer_mesures(e.texte, mesures, normaliser(dictee))
        if not reparees:
            continue
        d.reparations[e.id] = texte
        for avant, origine in reparees:
            d.alertes.append(Alerte(
                id=nid(), type="unite", gravite="attention",
                message=(f"Mesure rétablie telle que dictée : la rédaction écrivait « {avant} », la dictée dit "
                         f"« {origine.texte} ». Aucune unité n'est convertie ni corrigée sans le pathologiste."),
                element_ids=[e.id], confiance=0.95,
                sources=[_src_dictee(origine.debut, origine.fin, dictee)], agent="Vérificateur d'unités",
                pourquoi="La rédaction avait changé l'unité ou l'écriture d'une mesure ; la forme dictée est rétablie.",
                calcul=f"« {avant} » → « {origine.texte} »",
                action="Vérifier que la mesure rétablie est bien celle dictée"))
    d.alertes = _sans_doublons(d.alertes)
    return d


def _sans_doublons(alertes: list[Alerte]) -> list[Alerte]:
    """Une meme alerte (type, message) n'apparait qu'une fois ; les elements concernes sont fusionnes."""
    vues: dict[tuple[str, str], Alerte] = {}
    res: list[Alerte] = []
    for a in alertes:
        cle = (a.type, a.message)
        if cle in vues:
            vues[cle].element_ids = list(dict.fromkeys([*vues[cle].element_ids, *a.element_ids]))
            continue
        vues[cle] = a
        res.append(a)
    return res


_DIMENSIONS_SANS_UNITE = re.compile(
    r"\b\d+(?:[.,]\d+)?\s*(?:x|×|par)\s*\d+(?:[.,]\d+)?(?:\s*(?:x|×|par)\s*\d+(?:[.,]\d+)?)?"
    r"(?![\d.,]*\s*(?:x|×|par|\d|mm|cm|µm|millim|centim|%|pour))", re.IGNORECASE)


def _cle_mesure(m: Mesure) -> tuple[tuple[float, ...], str]:
    return tuple(round(v, 3) for v in m.valeurs), m.unite


_UNITE_DICTEE = {"mm": r"(?:mm|millimetres?)", "cm": r"(?:cm|centimetres?)", "µm": r"(?:µm|um|microns?)"}


def _valeur_avec_unite(v: float, unite: str, dictee_norm: str) -> bool:
    """La valeur est-elle dictee suivie de la MEME unite, a quelques mots pres (« 12 et 15 mm ») ?"""
    motif = rf"(?<![\d,.]){re.escape(formater_valeur(v))}(?![\d,])[^.;\n]{{0,15}}?{_UNITE_DICTEE.get(unite, unite)}\b"
    return re.search(motif, dictee_norm) is not None


def reparer_mesures(texte: str, mesures_dictee: list[Mesure],
                    dictee_norm: str = "") -> tuple[str, list[tuple[str, Mesure]], list[Mesure]]:
    """Retablit dans ``texte`` toute mesure dont l'unite ou l'ecriture differe de la dictee.

    - meme valeur, autre unite (« 25 mm » ecrit pour « 25 cm » dicte) -> forme dictee ;
    - meme longueur convertie (« 2,5 cm » pour « 25 mm ») -> forme dictee ;
    - mesure sans correspondant unique dans la dictee -> non reparable (le
      verificateur de securite retire alors l'element).
    Renvoie (texte repare, [(avant, mesure dictee)], [mesures non reparables]).
    """
    dictees = {_cle_mesure(m) for m in mesures_dictee}
    valeurs_seules = {v for m in mesures_dictee for v in (round(x, 3) for x in m.valeurs)}
    reparees: list[tuple[str, Mesure]] = []
    non_reparables: list[Mesure] = []
    for me in sorted(extraire_mesures(texte), key=lambda m: -m.debut):
        if _cle_mesure(me) in dictees:
            continue
        vals = tuple(round(v, 3) for v in me.valeurs)
        vals_mm = tuple(round(v, 3) for v in me.valeurs_mm)
        meme_valeur = [m for m in mesures_dictee if tuple(round(v, 3) for v in m.valeurs) == vals]
        meme_longueur = [m for m in mesures_dictee if tuple(round(v, 3) for v in m.valeurs_mm) == vals_mm]
        origine = (meme_valeur if len(meme_valeur) == 1 else meme_longueur if len(meme_longueur) == 1 else [None])[0]
        if origine is None:
            # Une valeur dictee AVEC la meme unite (« 12 et 15 mm », « 3 » de « 3 x 2 mm ») n'est pas
            # une invention. Une unite AJOUTEE a des dimensions dictees sans unite, si.
            if not all(v in valeurs_seules or _valeur_avec_unite(v, me.unite, dictee_norm) for v in vals):
                non_reparables.append(me)
            continue
        reparees.append((me.texte, origine))
        texte = texte[:me.debut] + origine.texte + texte[me.fin:]
    return texte, reparees, non_reparables


# ---------------------------------------------------------------------------
# 2. Coherence (C1-C16 + lateralite dictee/projet)
# ---------------------------------------------------------------------------

_GANGLIONS_EXAMINES = re.compile(
    r"(\d+)\s+ganglions?\s+(?:lymphatiques?\s+)?(?:examin|analys|prelev|isol|identifi|retrouv)", re.IGNORECASE)
_GANGLIONS_ENVAHIS = re.compile(
    r"(\d+)\s+(?:ganglions?\s+)?(?:sont\s+)?(?:metastatiques?|envahis?|positifs?|atteints?|metastases?)",
    re.IGNORECASE)


def ganglions_incoherents(texte_chiffre: str):
    """C4 etendu : « 3 ganglions examines ... 5 ganglions metastatiques » dans des phrases separees.

    Ne conclut que si le texte annonce UN seul total examine et UN seul total envahi
    (un CR par station ne se compare pas ainsi : abstention).
    """
    from reports.coherence_document import AlerteDocument, Empan
    norm = normaliser(texte_chiffre)
    examines = {int(m.group(1)) for m in _GANGLIONS_EXAMINES.finditer(norm)}
    envahis_m = list(_GANGLIONS_ENVAHIS.finditer(norm))
    envahis = {int(m.group(1)) for m in envahis_m}
    if len(examines) != 1 or len(envahis) != 1:
        return None
    n_ex, n_env = examines.pop(), envahis.pop()
    if n_env <= n_ex:
        return None
    return AlerteDocument("C4", f"{n_env} ganglions envahis rapportés pour {n_ex} examinés : le nombre "
                                f"d'envahis ne peut pas dépasser celui des examinés.")


#: Regles du catalogue qui relevent de la COMPLETUDE (deja couverte par la base v3,
#: champ par champ, avec zero faux positif) et non de l'incoherence : ecartees ici.
REGLES_ECARTEES: frozenset[str] = frozenset({"C8", "C9", "C15", "C16"})


_ACTIONS_REGLE: dict[str, str] = {
    "C1": "Vérifier la numérotation des blocs dans la dictée", "C2": "Vérifier le nombre de prélèvements annoncé",
    "C3": "Vérifier la somme des ganglions par station", "C4": "Vérifier les nombres de ganglions dictés",
    "C5": "Vérifier le nombre de fragments en macroscopie et en microscopie",
    "C6": "Vérifier la taille annoncée en conclusion", "C7": "Harmoniser l'unité (mm ou cm) dans le paragraphe",
    "C10": "Vérifier que la lésion de la conclusion est décrite en microscopie",
    "C11": "Vérifier que le marqueur de la conclusion figure dans l'immunohistochimie",
    "C12": "Relire la négation dans la dictée", "C13": "Vérifier le côté dicté", "C14": "Vérifier l'organe dicté",
}


def _libelle_regle(ref: "Referentiel | None", code: str) -> str:
    """Libelle de la regle Cn dans la base (« Ganglions envahis <= ganglions examines »), sinon ''. """
    if ref is None:
        return ""
    try:
        for r in ref._kb_appel("regles", defaut=[]) or []:
            if str(r.get("id", "")).startswith(f"regle:{code.lower()}_"):
                return str(r.get("libelle") or "")
    except Exception:  # noqa: BLE001
        pass
    return ""


def verifier_coherence(dictee: str, titre: str, sections: list[Section], elements: list[Element],
                       ref: "Referentiel | None" = None, organe_id: str | None = None) -> Decision:
    d = Decision()
    nid = _Ids("i")
    # Les regles historiques lisent des CHIFFRES : la dictee vocale ecrit souvent « cinq ».
    chiffres = [e.model_copy(update={"texte": chiffrer(e.texte)}) for e in elements]
    cr, positions = rendu_controle(titre, sections, chiffres)
    dictee_chiffree = chiffrer(dictee)
    regles = [a for a in verifier_coherence_document(cr, dictee_chiffree) if a.regle not in REGLES_ECARTEES]
    src = _src_regle("src:coherence_document", "Règles de cohérence documentaire MARC")
    for a in regles:
        ids = elements_touches(positions, a.empan.debut, a.empan.fin) if a.empan else []
        d.alertes.append(Alerte(
            id=nid(), type="incoherence", gravite="attention", message=f"{a.regle} : {a.message}",
            element_ids=ids, confiance=0.85,
            sources=[src.model_copy(update={"libelle": f"Règle {a.regle} (cohérence documentaire)"})],
            agent="Vérificateur de cohérence",
            pourquoi=(f"Règle {a.regle}"
                      + (f" ({_libelle_regle(ref, a.regle)[:1].lower()}{_libelle_regle(ref, a.regle)[1:]})" if _libelle_regle(ref, a.regle) else "")
                      + " : le texte ne la respecte pas."),
            action=_ACTIONS_REGLE.get(a.regle, "Relire le passage concerné et corriger la dictée si besoin")))
    # La dictee elle-meme peut etre incoherente (ganglions envahis > examines).
    c4 = regle_c4_envahis_inferieur_examines(dictee_chiffree) or ganglions_incoherents(dictee_chiffree)
    if c4 is not None and not any(a.message.startswith("C4") for a in d.alertes):
        srcs = [src]
        d.alertes.append(Alerte(id=nid(), type="incoherence", gravite="bloquant",
                                message=f"{c4.regle} (dictée) : {c4.message}", confiance=0.9,
                                sources=srcs, agent="Vérificateur de cohérence",
                                pourquoi="Le nombre de ganglions envahis ne peut pas dépasser le nombre de ganglions examinés.",
                                calcul=_calcul_c4(dictee_chiffree),
                                action="Vérifier les deux nombres dans la dictée"))
    # Lateralite : le projet ne doit pas changer de cote.
    cote_dictee = _lateralite_unique(dictee)
    texte_projet = "\n".join(e.texte for e in elements if e.type != "trou") + "\n" + titre
    cote_projet = _lateralite_unique(texte_projet)
    if cote_dictee and cote_projet and cote_dictee != cote_projet:
        ids = [e.id for e in elements if e.type != "trou" and _lateralite_unique(e.texte) == cote_projet]
        d.alertes.append(Alerte(
            id=nid(), type="incoherence", gravite="bloquant",
            message=f"Latéralité divergente : la dictée indique « {cote_dictee} », le projet « {cote_projet} ».",
            element_ids=ids, confiance=0.9, sources=[_src_regle("src:coherence_document", "Règle C13 latéralité")],
            agent="Vérificateur de cohérence",
            pourquoi="Le côté du projet n'est pas celui de la dictée ; MARC ne change jamais un côté dicté.",
            calcul=f"dictée : {cote_dictee} ≠ projet : {cote_projet}",
            action="Vérifier le côté et corriger le projet"))
        for i in ids:
            d.retraits[i] = f"latéralité « {cote_projet} » non dictée (dictée : « {cote_dictee} »)"
    for a in _incoherences_dictee(dictee_chiffree, titre, elements):
        d.alertes.append(a.model_copy(update={"id": nid()}))
    if ref is not None:  # regles arithmetiques de la base (pN, pT, pourcentages, SBR, Gleason, Ki67)
        from projet.regles_arith import concerne, controles
        for c in controles(dictee_chiffree, ref, organe_id):
            if not c.declenche or not c.alerter:
                continue
            ids = [e.id for e in elements if e.type != "trou" and concerne(c, e.texte)]
            d.alertes.append(Alerte(
                id=nid(), type="incoherence", gravite=c.gravite, message=f"{c.code} : {c.detail}",  # type: ignore[arg-type]
                element_ids=ids, suggestion=c.suggestion, confiance=0.85, sources=[c.source],
                agent="Vérificateur de cohérence", pourquoi=c.titre + " : " + c.detail,
                calcul=c.calcul, action=c.action))
    d.alertes = _sans_doublons(d.alertes)
    d.details.append(f"{len(d.alertes)} incohérence(s) ; règles C1-C16 + latéralité + fractions + taille évaluées")
    return d


#: « 3 carottes positives sur 2 prelevees » : une partie ne depasse jamais le tout.
_FRACTION = re.compile(
    r"(\d+)\s+(carottes?|fragments?|biopsies?|prelevements?|blocs?|cassettes?)\b[^.;\n]{0,40}?\bsur\s+(\d+)\b")

_COTES_ORGANES = re.compile(
    r"\b(sein|poumon|rein|ovaire|testicule|amygdale|parotide|trompe|lobe thyroidien|thyroide|oeil|oreille|"
    r"cuisse|bras|jambe|avant-bras|epaule|genou|hanche|joue|ovaires)\s+(droit|droite|gauche)\b")

_LEGITIME_DEUX_COTES = re.compile(r"bilateral|controlateral|homolateral|prelevement|specimen|echantillon|\n\s*\d+\s*[).]|"
                                  r"droit et gauche|gauche et droit|les deux|numero|piece")


def _calcul_c4(dictee_chiffree: str) -> str | None:
    norm = normaliser(dictee_chiffree)
    ex = {int(m.group(1)) for m in _GANGLIONS_EXAMINES.finditer(norm)}
    env = {int(m.group(1)) for m in _GANGLIONS_ENVAHIS.finditer(norm)}
    if len(ex) == 1 and len(env) == 1:
        return f"{env.copy().pop()} envahis > {ex.copy().pop()} examinés"
    return None


def _incoherences_dictee(dictee_chiffree: str, titre: str, elements: list[Element]) -> list[Alerte]:
    """Incoherences internes a la dictee (ou entre conclusion et macroscopie) que C1-C16 ne couvrent pas."""
    res: list[Alerte] = []
    norm = normaliser(dictee_chiffree)
    src = _src_regle("src:coherence_document", "Règle d'incohérence interne de la dictée")
    # 1. partie > tout
    for m in _FRACTION.finditer(norm):
        partie, tout = int(m.group(1)), int(m.group(3))
        if partie > tout:
            res.append(Alerte(
                id="f", type="incoherence", gravite="bloquant",
                message=(f"Dictée incohérente : {partie} {m.group(2)} annoncée(s) « sur {tout} » - la partie "
                         f"ne peut pas dépasser le total."), confiance=0.9, sources=[src],
                agent="Vérificateur de cohérence",
                pourquoi="Une partie ne peut pas dépasser le total annoncé.",
                calcul=f"{partie} > {tout}", action="Vérifier les deux nombres dans la dictée"))
            break
    # 2. cote contradictoire pour le meme organe (hors prelevements distincts ou bilateral)
    cotes: dict[str, set[str]] = {}
    for m in _COTES_ORGANES.finditer(norm):
        cotes.setdefault(m.group(1).rstrip("s"), set()).add("droit" if m.group(2).startswith("droit") else "gauche")
    contradictoires = [o for o, c in cotes.items() if len(c) > 1]
    if contradictoires and not _LEGITIME_DEUX_COTES.search(norm):
        res.append(Alerte(
            id="l", type="incoherence", gravite="attention",
            message=(f"Latéralité contradictoire dans la dictée pour : {', '.join(sorted(contradictoires))} "
                     f"(droit et gauche sont tous deux cites)."), confiance=0.85, sources=[src],
            agent="Vérificateur de cohérence",
            pourquoi="Un même organe est dicté à droite et à gauche, sans mention de bilatéralité ni de prélèvements distincts.",
            calcul="droit ≠ gauche pour le même organe", action="Vérifier le côté de chaque organe dans la dictée"))
    # 3. taille annoncee en conclusion superieure a toute mesure de la macroscopie et de la microscopie
    def _mm(section: str) -> list[float]:
        txt = " ".join(e.texte for e in elements if e.type != "trou" and e.section_id == section)
        return [max(m.valeurs_mm) for m in extraire_mesures(chiffrer(txt)) if m.valeurs_mm
                and m.objet in (None, "tumeur", "polype", "piece")]
    concl, macro, micro = _mm("conclusion"), _mm("macroscopie"), _mm("microscopie")
    if concl and macro:
        taille, plus_grande = max(concl), max(macro + micro)
        if taille > plus_grande * 1.05:
            ids = [e.id for e in elements if e.section_id == "conclusion" and e.type != "trou"
                   and any(abs(max(m.valeurs_mm) - taille) < 0.01 for m in extraire_mesures(chiffrer(e.texte)) if m.valeurs_mm)]
            res.append(Alerte(
                id="t", type="incoherence", gravite="attention",
                message=(f"Taille de la conclusion ({formater_valeur(taille)} mm) supérieure à la plus grande "
                         f"mesure de la macroscopie/microscopie ({formater_valeur(plus_grande)} mm)."),
                element_ids=ids, confiance=0.8, sources=[_src_regle("src:coherence_document", "Règle C6 élargie")],
                agent="Vérificateur de cohérence",
                pourquoi="La taille de la conclusion ne peut pas dépasser la plus grande mesure décrite plus haut.",
                calcul=f"{formater_valeur(taille)} mm > {formater_valeur(plus_grande)} mm (x 1,05 de tolérance)",
                action="Vérifier la taille dans la conclusion et dans la macroscopie"))
    return res


# ---------------------------------------------------------------------------
# 3. Completude (zero faux positif)
# ---------------------------------------------------------------------------

#: Racines morphologiques : leur presence (non niee) renseigne le type histologique.
_RACINES_MORPHO = re.compile(
    r"carcinome|adenome|\badk\b|melanome|sarcome|lymphome|mesotheliome|seminome|blastome|gliome|"
    r"neoplasie|lesion malpighienne|\bcin ?[1-3]\b|\bain ?[1-3]\b|hsil|lsil|carcinoide|neuroendocrine|"
    r"papillome|condylome|naevus|tumeur (?:phyllode|a cellules|neuro|stromale|germinale)")

#: Mots-cles de detection trop generiques pour prouver la presence d'un champ precis.
_MOTS_CLES_GENERIQUES: frozenset[str] = frozenset({
    "score", "grade", "proliferation", "vasculaire", "vasculaires", "lymphatiques", "taille", "type",
    "aspect", "nombre", "presence", "absence", "statut", "infiltrant", "tumeur", "lesion", "cellules",
})

#: Champs qui n'ont de sens que si une entite precise est dictee (sinon : non applicable,
#: jamais reclame). (motif sur le libelle normalise, motif requis dans la dictee normalisee)
_DEPENDANCES: list[tuple[re.Pattern[str], re.Pattern[str]]] = [
    (re.compile(r"grade nucleaire du ccis|micro-?invasion"), re.compile(r"ccis|in situ|intracanalaire")),
    (re.compile(r"sous-type d.adenocarcinome|pattern predominant"), re.compile(r"adenocarcinome")),
    (re.compile(r"pattern 4/5|cribriforme"), re.compile(r"gleason|isup|pattern")),
    (re.compile(r"vesicules? seminales?"), re.compile(r"prostatectomie|vesicules? seminales?")),
    (re.compile(r"mesorectum|circonferentielle|\bcrm\b"), re.compile(r"rectum|rectal|recto|mesorectum")),
]


_STADE_DICTE = re.compile(r"(?<![a-z0-9])(?:y?p|c)?(?:t(?:is|[0-4x])[a-d]?|n[0-3x][a-c]?|m[01x])(?![a-z0-9])")


def champ_present(champ: ChampAttendu, dictee: str, extraction: Extraction | None,
                  contexte: str = "indetermine") -> bool:
    """Le champ est-il DEJA dicte ? Biais volontaire : dans le doute, oui (zero faux positif).

    Preuves (une seule suffit) : un fait extrait rattache au champ, un mot-cle
    de detection du champ dans la dictee (meme nie : « pas d'emboles » renseigne
    le champ emboles), ou le filtre historique ``filter_present_alertes``.
    Le « diagnostic lesionnel » est present des qu'une nature lesionnelle est dictee.
    """
    if extraction is not None and any(f.champ_id == champ.id for f in extraction.faits):
        return True
    if champ.concept == "type_histologique" and _RACINES_MORPHO.search(mask_negations(normaliser(dictee))):
        return True  # un type lesionnel est dicte (adenome tubuleux, adenocarcinome...) : champ renseigne
    if champ.concept in ("taille_tumorale", "taille_tumorale_ccis") and any(
            m.objet in ("tumeur", "polype") for m in extraire_mesures(dictee)):
        return True  # une mesure de la tumeur/masse/lesion/nodule est dictee
    if champ.concept == "ptnm" and _STADE_DICTE.search(normaliser(dictee)):
        return True  # un stade (pT3, N1a, ypT0...) est dicte : le champ est renseigne
    if champ.concept == "diagnostic_lesionnel":
        if contexte != "indetermine" or "conclusion" in normaliser(dictee):
            return True
        if extraction is not None and any(f.section in ("conclusion", "microscopie") for f in extraction.faits):
            return True
    norm = normaliser(dictee)
    for mot in champ.mots_cles:
        m = normaliser(mot).strip()
        if m in _MOTS_CLES_GENERIQUES:
            continue  # « score », « proliferation »... ne prouvent pas que CE champ est dicte
        if len(m) >= 2 and contient_terme(norm, m):
            return True
    restants, retires = filter_present_alertes(
        [DonneeManquante(champ=champ.libelle, description=champ.libelle, section=champ.section)], dictee)
    return retires > 0 or not restants


def champ_applicable_dictee(champ: ChampAttendu, dictee: str) -> bool:
    """Un champ dependant d'une entite (CCIS, adenocarcinome...) n'est attendu que si elle est dictee."""
    lib, norm = normaliser(champ.libelle), normaliser(dictee)
    return all(requis.search(norm) for motif, requis in _DEPENDANCES if motif.search(lib))


def champs_manquants(champs: list[ChampAttendu], dictee: str, extraction: Extraction | None,
                     contexte: str = "indetermine") -> list[ChampAttendu]:
    """Champs obligatoires applicables ET non dictes."""
    return [c for c in champs if champ_applicable_dictee(c, dictee)
            and not champ_present(c, dictee, extraction, contexte)]


def verifier_completude(dictee: str, champs: list[ChampAttendu], elements: list[Element],
                        extraction: Extraction | None, contexte: str = "indetermine") -> Decision:
    """Trous a ajouter (champs absents) et a retirer (champ dicte ou non applicable)."""
    d = Decision()
    nid = _Ids("m")
    attendus = {c.id: c for c in champs if champ_applicable_dictee(c, dictee)}
    manquants = champs_manquants(champs, dictee, extraction, contexte)
    ids_manquants = {c.id for c in manquants}
    trous_existants = {e.champ_id: e for e in elements if e.type == "trou" and e.champ_id}
    for e in elements:
        if e.type != "trou":
            continue
        if e.champ_id not in attendus:
            d.trous_a_retirer[e.id] = "champ non applicable à ce contexte (filtre de sécurité)"
        elif e.champ_id not in ids_manquants:
            d.trous_a_retirer[e.id] = "champ déjà dicté"
    couverts = {e.champ_id for e in elements if e.type != "trou" and e.champ_id}
    for c in manquants:
        if c.id in couverts:
            continue
        if c.id not in trous_existants:
            d.trous_a_ajouter.append(c)
        d.alertes.append(Alerte(
            id=nid(), type="manquant", gravite="attention",
            message=f"Champ obligatoire non dicté : {c.libelle}.",
            suggestion=("Valeurs possibles : " + ", ".join(c.options[:8])) if c.options else None,
            confiance=c.confiance_source, sources=[c.source_exigence] if c.source_exigence else [],
            agent="Vérificateur de complétude",
            pourquoi=(f"« {c.libelle} » est exigé pour ce type de compte rendu"
                      + (f" ({c.source_exigence.libelle})" if c.source_exigence else "") + " et rien dans la dictée ne le renseigne."),
            calcul=f"0 mention trouvée pour : {', '.join(c.mots_cles[:4])}" if c.mots_cles else None,
            action=("Dicter la valeur ou la saisir dans le champ à compléter"
                    + (" (" + ", ".join(c.options[:4]) + ")" if c.options else ""))))
    d.details.append(f"{len(champs)} champ(s) attendu(s), {len(manquants)} non dicté(s)")
    return d


# ---------------------------------------------------------------------------
# 4. Securite (garde-chiffres, negations, pTNM, perimetre biopsie)
# ---------------------------------------------------------------------------

_NOMBRE_ISOLE = re.compile(r"(?<![A-Za-z0-9\-/])\d+(?:[.,]\d+)?(?![A-Za-z0-9])")
_TNM = re.compile(r"\b(?:y?p|c)?[TNM](?:is|[0-4xX])[a-d]?\b")
_NUMEROTATION = re.compile(r"(?m)^\s*\d{1,2}\s*[).°-]")
_MOTS_MARGE = ("marge", "limite d'exerese", "limites d'exerese", "recoupe", "berge")


#: Constatations dont la negation change le sens clinique. Le controle d'inversion ne
#: porte que sur elles : « curage ganglionnaire » n'affirme pas un envahissement.
_CONSTATATIONS = re.compile(
    r"^(?:embole|engainement|envahissement|metasta|invasion|infiltr|necrose|ulcera|mitose|atypie|dysplasie|"
    r"carcinom|adenocarcinom|malignit|effraction|rupture|microsatellit|regression|perforation|depot|"
    r"helicobacter|granulome|koilocyt|calcification|thrombose|rejet|tumora|proliferation)")


def _termes_significatifs(texte: str) -> set[str]:
    return {m for m in re.findall(r"[a-z]{6,}", normaliser(texte)) if _CONSTATATIONS.match(m)}


#: Une negation ne couvre pas la proposition suivante : « pas de carcinome in situ MAIS carcinome infiltrant ».
_PROPOSITIONS = re.compile(r"[.;\n]|\b(?:mais|cependant|toutefois|sauf|en revanche|par contre)\b", re.IGNORECASE)


def verifier_securite(dictee: str, elements: list[Element], prelevement: str | None,
                      titre: str = "", ignorer: list[tuple[int, int, str]] | None = None) -> Decision:
    """Tout contenu non dicte detectable deterministiquement est RETIRE."""
    d = Decision()
    nid = _Ids("s")
    dictee_n = dictee + "\n" + chiffrer(dictee)  # « zero virgule trois » est dicte : 0,3 aussi
    nombres_dictes = source_number_set(dictee_n)
    norm_dictee = normaliser(dictee)
    masque_dictee = mask_negations(norm_dictee)
    src = _src_regle("src:garde_fous", "Garde-fous MARC")
    mesures_dictee = extraire_mesures(dictee)
    for e in elements:
        if e.type == "trou":
            continue
        raisons: list[str] = []
        # a) chiffres porteurs non dictes (mesures, ganglions, mitoses...)
        porteurs = chiffres_non_dictes(e.texte, dictee_n)
        if porteurs:
            raisons.append("chiffre(s) non dicté(s) : " + ", ".join(porteurs))
        # b) tout nombre isole absent de la dictee (ex. Gleason 7 deduit de 3+4)
        texte_num = _NUMEROTATION.sub("", e.texte)  # numerotation de prelevements : pas une donnee
        for n in _NOMBRE_ISOLE.findall(texte_num):
            parties = re.split(r"[.,]", n)
            if not all(p in nombres_dictes for p in parties) and n.replace(",", ".") not in nombres_dictes:
                raisons.append(f"nombre « {n} » absent de la dictée")
                break
        # b2) mesure (valeur + unite) sans correspondant dans la dictee, non reparable
        _, _, inventees = reparer_mesures(e.texte, mesures_dictee, norm_dictee)
        if inventees:
            raisons.append("mesure(s) absente(s) de la dictée : " + ", ".join(m.texte for m in inventees))
        # c) pTNM non dicte
        for t in _TNM.findall(e.texte):
            if normaliser(t) not in norm_dictee:
                raisons.append(f"stade « {t} » non dicté")
                break
        # d) negation inversee (affirme ce que la dictee nie, ou l'inverse)
        norm_e = normaliser(e.texte)
        masque_e = mask_negations(norm_e)
        for terme in _termes_significatifs(e.texte):
            if terme not in norm_dictee:
                continue
            affirme_e = terme in masque_e
            nie_e = not affirme_e
            if affirme_e and est_nie(dictee, terme):
                raisons.append(f"« {terme} » affirmé alors que la dictée le nie")
                break
            if nie_e and terme in masque_dictee and not any(
                    terme in normaliser(x) and est_nie(x, terme) for x in _PROPOSITIONS.split(dictee)):
                raisons.append(f"« {terme} » nie alors que la dictée l'affirme")
                break
        # e) marges sur une biopsie, non dictees
        if prelevement == "biopsie" and any(contient_terme(norm_e, m) for m in _MOTS_MARGE) \
                and not any(contient_terme(norm_dictee, m) for m in _MOTS_MARGE):
            raisons.append("marges évoquées sur une biopsie sans être dictées")
        if raisons:
            d.retraits[e.id] = " ; ".join(raisons)
            d.alertes.append(Alerte(
                id=nid(), type="securite", gravite="bloquant",
                message=f"Élément retiré (contenu non dicté) : « {extrait_court(e.texte, 140)} » - {raisons[0]}.",
                element_ids=[e.id], confiance=0.95, sources=[src], agent="Vérificateur de sécurité",
                pourquoi="La rédaction contenait une information absente de la dictée ; MARC n'ajoute rien qui n'ait été dicté.",
                calcul=" ; ".join(raisons) if any(raisons[0].startswith(x) for x in ("chiffre", "nombre", "mesure", "stade")) else None,
                action="Le passage dicté est repris à la place : vérifier qu'il convient"))
    d.omissions = [o for o in verifier_omissions(dictee, elements, titre)
                   if not any(o[0] < f and o[1] > g for g, f, _ in ignorer or [])]  # injections : deja signalees
    for debut, fin, texte in d.omissions:
        d.alertes.append(Alerte(
            id=nid(), type="securite", gravite="attention",
            message=f"Passage dicté non repris par la rédaction, ajouté tel quel : « {extrait_court(texte, 140)} ».",
            confiance=0.9, sources=[_src_dictee(debut, fin, dictee)], agent="Vérificateur de sécurité",
            pourquoi=(f"Cette phrase dictée n'était reprise par aucun élément (moins de {int(SEUIL_COUVERTURE * 100)} % "
                      "de ses mots, ou l'un de ses nombres, retrouvés) : rien ne doit se perdre."),
            calcul=None, action="La phrase est ajoutée telle quelle : la reformuler si besoin"))
    d.details.append(f"{len(d.retraits)} élément(s) retiré(s) par les garde-fous, "
                     f"{len(d.omissions)} passage(s) dicté(s) omis")
    return d


_ENTETES_DICTES = re.compile(
    r"^\W*(renseignements?( cliniques?)?|macroscopie|microscopie|examen \w+|immunohistochimie|"
    r"conclusion|histologie|cytologie)\W*$", re.IGNORECASE)


#: Part minimale des mots porteurs d'une phrase dictee qui doit se retrouver dans le projet.
SEUIL_COUVERTURE: float = 0.8


def verifier_omissions(dictee: str, elements: list[Element], titre: str = "") -> list[tuple[int, int, str]]:
    """Phrases dictees reprises par AUCUN element.

    La fidelite vaut dans les deux sens : rien d'ajoute, rien de perdu. Une phrase
    est couverte si un element la cite (empan) ou si au moins 80 % de ses mots
    porteurs ET tous ses nombres se retrouvent dans le projet. Une phrase omise
    est rendue au projet telle quelle par l'orchestrateur.
    """
    from etude.ancrage import _correspond, decouper, jetons_discriminants
    from projet.textes import phrases

    spans = [(s.debut, s.fin) for e in elements for s in e.sources
             if s.kind == "dictee" and s.debut is not None and s.fin is not None]
    texte_projet = titre + "\n" + "\n".join(e.texte for e in elements if e.type != "trou")
    formes = {j.forme for j in decouper(texte_projet)}
    nombres_projet = source_number_set(texte_projet)
    omises: list[tuple[int, int, str]] = []
    for debut, fin, texte in phrases(dictee):
        attendus = set(jetons_discriminants(texte))
        nombres = {n for n in re.findall(r"\d+", texte)} | {
            str(int(v)) for m in extraire_mesures(texte) for v in m.valeurs if float(v).is_integer()}
        if _ENTETES_DICTES.match(texte.strip()) or (len(attendus) < 2 and not nombres):
            continue
        # Une phrase « citee » par un element (un simple titre) peut avoir perdu ses nombres : on ne
        # la tient pour couverte que si tous ses nombres figurent dans le projet.
        if any(debut < f and fin > d for d, f in spans) and nombres <= nombres_projet:  # type: ignore[operator]
            continue
        couverts = sum(1 for t in attendus if any(_correspond(t, f) for f in formes))
        if (not attendus or couverts / len(attendus) >= SEUIL_COUVERTURE) and nombres <= nombres_projet:
            continue
        omises.append((debut, fin, texte))
    return omises


_GROUPE_STADE = re.compile(
    r"(?<![A-Za-z0-9])(?:y?p|c)?T(?:is|[0-4xX])[a-d]?(?:\s*,?\s*(?:y?p|c)?N[0-3xX][a-c]?)?(?:\s*,?\s*(?:y?p|c)?M[01xX])?"
    r"(?![A-Za-z0-9])")


def stades_perdus(dictee: str, elements: list[Element], titre: str = "") -> list[tuple[int, int, str]]:
    """Stades pTNM DICTES (« pT3 N1a ») qui ne figurent dans aucun element : (debut, fin, texte).

    Un stade n'est jamais deduit, mais il ne doit jamais non plus se perdre : la phrase de
    conclusion peut etre bien couverte par la redaction tout en omettant le stade.
    """
    texte_projet = normaliser(titre + "\n" + "\n".join(e.texte for e in elements if e.type != "trou"))
    perdus: list[tuple[int, int, str]] = []
    for m in _GROUPE_STADE.finditer(dictee):
        morceaux = _TNM.findall(m.group(0))
        if morceaux and any(normaliser(t) not in texte_projet for t in morceaux):
            perdus.append((m.start(), m.end(), m.group(0).strip()))
    return perdus


def verifier_citations(elements: list[Element], dictee: str) -> list[str]:
    """Controle de contrat : chaque source dictee pointe bien dans la dictee."""
    erreurs = []
    for e in elements:
        for s in e.sources:
            if s.kind == "dictee":
                if s.debut is None or s.fin is None or not (0 <= s.debut < s.fin <= len(dictee)):
                    erreurs.append(f"{e.id} : empan invalide")
    return erreurs


__all__ = [
    "Decision", "verifier_unites", "verifier_coherence", "verifier_completude", "verifier_securite",
    "champ_present", "verifier_citations", "localiser_exacte",
]
