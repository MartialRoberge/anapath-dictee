"""Preuves lisibles d'un element : pourquoi cette phrase est la, pourquoi elle est a relire.

Liste courte (3 a 6) et TOUJOURS dans le meme ordre : dictee -> regle -> referentiel -> modele.
Les regles sont deterministes (arithmetique, plages, negations, coherence) et passent avant
le jugement du modele. Chaque facteur de ``confiance.decomposer`` devient une preuve et porte
sa contribution dans ``effet`` : la somme des ``effet`` donne la confiance affichee (la preuve de
dictee porte la base d'ancrage ; un ajustement residuel, rare, est ecrit dans la preuve modele).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from etude.ancrage import _correspond, decouper, jetons_discriminants
from negation import est_nie, mask_negations
from projet import confiance as conf_mod
from projet.mesures import chiffrer, extraire_mesures, formater_valeur
from projet.referentiel import ChampAttendu, OrganeDetecte, Referentiel
from projet.regles_arith import Controle, concerne
from projet.schemas import Alerte, Element, Preuve, SourceRef
from projet.textes import contient_terme, extrait_court
from projet.verificateurs import (
    _MOTS_CLES_GENERIQUES,
    _NOMBRE_ISOLE,
    _NUMEROTATION,
    _termes_significatifs,
    avec_article as _avec_article,
    calcul_plage,
)
from reports.numbers import source_number_set
from text_utils import normaliser

if TYPE_CHECKING:
    from projet.relecteur import Verdict

MAX_PREUVES = 6
_ORDRE_CATEGORIE = {"dictee": 0, "regle": 1, "referentiel": 2, "modele": 3}
_GRAVITE_VERDICT = {"echec": 0, "attention": 1, "info": 2, "ok": 3}


def _fmt(x: float) -> str:
    return f"{x:+.2f}".replace(".", ",").replace("-", "−")


@dataclass(slots=True)
class _P:
    """Preuve en construction : la raison (pour ``a_verifier``) et son rang d'affichage."""

    preuve: Preuve
    raison: str = ""
    rang: int = 0           # ordre fixe a l'interieur d'une categorie
    obligatoire: bool = False


@dataclass(slots=True)
class Contexte:
    """Tout ce dont la construction des preuves a besoin (un seul objet, pas de signature a rallonge)."""

    dictee: str
    ref: Referentiel
    organe: OrganeDetecte | None = None
    prelevement: str | None = None
    champs: list[ChampAttendu] = field(default_factory=list)
    controles: list[Controle] = field(default_factory=list)
    alertes: list[Alerte] = field(default_factory=list)
    corrections: list = field(default_factory=list)
    modele_relecteur: str = ""
    #: contexte lesionnel detecte (malin, benin, precancereux, indetermine)
    contexte: str = ""


# ---------------------------------------------------------------------------
# dictee
# ---------------------------------------------------------------------------

def _empan_dictee(element: Element, dictee: str) -> SourceRef | None:
    srcs = [s for s in element.sources if s.kind == "dictee" and s.debut is not None and s.fin is not None]
    if not srcs:
        return None
    debut, fin = min(s.debut for s in srcs), max(s.fin for s in srcs)  # type: ignore[type-var]
    if len(srcs) == 1:
        extrait = srcs[0].extrait or extrait_court(dictee[debut:fin])
    else:
        extrait = extrait_court(" … ".join(s.extrait or dictee[s.debut:s.fin] for s in srcs))
    return SourceRef(kind="dictee", ref="dictee", libelle="Dictée", extrait=extrait_court(extrait), debut=debut, fin=fin)


def _preuve_dictee(element: Element, ancrage: str | None, base: float, ctx: Contexte) -> _P:
    src = _empan_dictee(element, ctx.dictee)
    extrait = f" : « {src.extrait} »" if src and src.extrait else ""
    calcul = None
    if ancrage == "exacte":
        verdict, detail = "ok", f"Passage retrouvé mot pour mot dans la dictée{extrait}."
    elif ancrage == "ancrage":
        verdict, detail = "info", f"Passage retrouvé par recouvrement de mots, pas mot pour mot{extrait}."
        if src and src.debut is not None:
            formes = [j.forme for j in decouper(ctx.dictee[src.debut:src.fin])]
            attendus = jetons_discriminants(element.texte)
            if attendus:
                trouves = sum(1 for t in attendus if any(_correspond(t, f) for f in formes))
                calcul = f"{trouves} mot(s) porteur(s) sur {len(attendus)} retrouvé(s) dans le passage"
    else:
        verdict, detail = "echec", "Aucun passage de la dictée ne justifie cette phrase."
    raison = {"ancrage": "La phrase est reformulée : le passage de la dictée n'est pas repris mot pour mot.",
              None: "Aucun passage de la dictée ne justifie cette phrase."}.get(ancrage, "")
    return _P(Preuve(categorie="dictee", verdict=verdict, titre="Passage de la dictée",  # type: ignore[arg-type]
                     detail=detail, calcul=calcul, source=src, effet=round(base, 4)), raison, 0, True)


def _preuve_phonetique(facteurs: list[conf_mod.Facteur]) -> _P | None:
    fs = [f for f in facteurs if f.code == "phonetique"]
    if not fs:
        return None
    effet = round(sum(f.effet for f in fs), 4)
    if len(fs) == 1:
        c = fs[0].ref
        detail = f"« {c.original} » a été corrigé en « {c.corrige} » (confiance {int(round(c.confiance * 100))} %)."  # type: ignore[union-attr]
        calcul = f"−(1 − {formater_valeur(c.confiance)}) × 0,5 = {_fmt(effet)}"  # type: ignore[union-attr]
        raison = f"« {c.original} » a été corrigé en « {c.corrige} » : vérifier le terme."  # type: ignore[union-attr]
        source = c.sources[0] if c.sources else None  # type: ignore[union-attr]
    else:
        detail = f"{len(fs)} termes ont été corrigés dans ce passage."
        calcul = " ".join(_fmt(f.effet) for f in fs) + f" = {_fmt(effet)}"
        termes = ", ".join(f"« {f.ref.original} » → « {f.ref.corrige} »" for f in fs if f.ref is not None)  # type: ignore[union-attr]
        raison = f"Termes corrigés à l'écoute : {termes} ; vérifier." if termes else "Plusieurs termes corrigés à l'écoute : vérifier."
        source = None
    return _P(Preuve(categorie="dictee", verdict="attention", titre="Correction phonétique dans le passage",
                     detail=detail, calcul=calcul, source=source, effet=effet), raison, 1, True)


# ---------------------------------------------------------------------------
# regles
# ---------------------------------------------------------------------------

_SRC_GARDE_FOUS = SourceRef(kind="regle", ref="src:garde_fous", libelle="Garde-fous MARC", fiabilite="B")


def _nombres_element(texte: str) -> list[str]:
    """Nombres portes par l'element (chiffres, et nombres ecrits en lettres), sans doublon, dans l'ordre."""
    sans_article = re.sub(r"\b(?:un|une)\b", "_", texte, flags=re.IGNORECASE)  # « une biopsie » n'est pas le nombre 1
    texte_num = _NUMEROTATION.sub("", chiffrer(sans_article))
    res: list[str] = []
    for n in _NOMBRE_ISOLE.findall(texte_num):
        if n not in res:
            res.append(n)
    return res


def _regle_chiffres(element: Element, ctx: Contexte) -> _P | None:
    nombres = _nombres_element(element.texte)
    if not nombres:
        return None
    dictes = source_number_set(ctx.dictee + "\n" + chiffrer(ctx.dictee))

    def present(n: str) -> bool:
        return all(p in dictes for p in re.split(r"[.,]", n)) or n.replace(",", ".") in dictes

    absents = [n for n in nombres if not present(n)]
    liste = ", ".join(nombres)
    if absents:
        a = ", ".join(absents)
        return _P(Preuve(categorie="regle", verdict="echec", titre="Chiffres conservés",
                         detail=f"Le nombre {a} ne figure pas dans la dictée." if len(absents) == 1
                         else f"Les nombres {a} ne figurent pas dans la dictée.",
                         calcul=f"{a} absent(s) de la dictée", source=_SRC_GARDE_FOUS),
                  f"{'Le nombre' if len(absents) == 1 else 'Les nombres'} {a} ne figure(nt) pas dans la dictée.", 0)
    return _P(Preuve(categorie="regle", verdict="ok", titre="Chiffres conservés",
                     detail=("Le nombre " if len(nombres) == 1 else "Les nombres ") + liste
                     + (" figure" if len(nombres) == 1 else " figurent") + " dans la dictée.",
                     calcul=f"{liste} présent(s) dans la dictée", source=_SRC_GARDE_FOUS), "", 0)


def _regle_negations(element: Element, ctx: Contexte) -> _P | None:
    norm_e = normaliser(element.texte)
    masque_e = mask_negations(norm_e)
    norm_d = normaliser(ctx.dictee)
    e_nie = masque_e != norm_e
    termes = [t for t in sorted(_termes_significatifs(element.texte)) if t in norm_d]
    verifies, fautifs = [], []
    for t in termes:
        affirme_e = t in masque_e
        d_nie = est_nie(ctx.dictee, t)
        if affirme_e and d_nie:
            fautifs.append((t, "affirmé dans l'élément alors que la dictée le nie"))
        elif not affirme_e and not d_nie and e_nie:
            fautifs.append((t, "nié dans l'élément alors que la dictée l'affirme"))
        elif d_nie or not affirme_e:
            verifies.append(t)
    if fautifs:
        t, pb = fautifs[0]
        return _P(Preuve(categorie="regle", verdict="echec", titre="Négations conservées",
                         detail=f"« {t} » est {pb}.", calcul=f"dictée : {'nié' if est_nie(ctx.dictee, t) else 'affirmé'} ; élément : "
                         f"{'affirmé' if t in masque_e else 'nié'}", source=_SRC_GARDE_FOUS),
                  f"« {t} » est {pb}.", 1)
    if verifies:
        t = verifies[0]
        return _P(Preuve(categorie="regle", verdict="ok", titre="Négations conservées",
                         detail=f"« {t} » est nié dans la dictée et dans l'élément.",
                         calcul="dictée : nié ; élément : nié", source=_SRC_GARDE_FOUS), "", 1)
    if e_nie:
        if masque_d_nie := (mask_negations(norm_d) != norm_d):
            return _P(Preuve(categorie="regle", verdict="ok", titre="Négations conservées",
                             detail="La négation de l'élément figure aussi dans la dictée.",
                             calcul="dictée : négation présente ; élément : négation présente", source=_SRC_GARDE_FOUS), "", 1)
        return _P(Preuve(categorie="regle", verdict="attention", titre="Négations conservées",
                         detail="L'élément contient une négation que la dictée ne contient pas.",
                         calcul="dictée : aucune négation ; élément : négation", source=_SRC_GARDE_FOUS),
                  "L'élément contient une négation que la dictée ne contient pas.", 1)
    return None


def _regle_plage(element: Element, ctx: Contexte) -> _P | None:
    mesures = extraire_mesures(chiffrer(element.texte))
    candidats: list[tuple[bool, object, object]] = []
    for m in mesures:
        categorie = m.objet or ("fragment" if ctx.prelevement == "biopsie" else None)
        if categorie is None:
            continue
        plage = ctx.ref.plage(ctx.organe.id if ctx.organe else None, categorie, ctx.prelevement)
        if plage is None:
            continue
        hors = not (plage.min_mm <= m.max_mm <= plage.max_mm)
        candidats.append((hors, m, plage))
    if not candidats:
        return None
    candidats.sort(key=lambda c: not c[0])  # une mesure hors plage prime
    hors, m, plage = candidats[0]
    calcul = calcul_plage(m, plage)  # type: ignore[arg-type]
    n_autres = len(candidats) - 1
    suite = f" (+ {n_autres} autre(s) mesure(s) dans la plage)" if n_autres and hors else ""
    if hors:
        valeurs = (" à " if m.intervalle else " x ").join(formater_valeur(v) for v in m.valeurs) + f" {m.unite}"  # type: ignore[attr-defined]
        if m.max_mm > plage.max_mm:  # type: ignore[attr-defined]
            raison = (f"{valeurs} est inhabituel pour {_avec_article(plage.contexte or plage.libelle)} "  # type: ignore[attr-defined]
                      f"(max {formater_valeur(plage.max_mm)} mm) : vérifier mm ou cm.")  # type: ignore[attr-defined]
        else:
            raison = (f"{valeurs} est inférieur au minimum habituel pour {_avec_article(plage.contexte or plage.libelle)} "  # type: ignore[attr-defined]
                      f"(min {formater_valeur(plage.min_mm)} mm) : vérifier mm ou cm.")  # type: ignore[attr-defined]
        return _P(Preuve(categorie="regle", verdict="attention", titre="Unité et plage de mesure",
                         detail=raison + suite, calcul=calcul, source=plage.source), raison, 2)  # type: ignore[attr-defined]
    return _P(Preuve(categorie="regle", verdict="ok", titre="Unité et plage de mesure",
                     detail=f"{m.texte} est dans la plage habituelle pour {_avec_article(plage.contexte or plage.libelle)}.",  # type: ignore[attr-defined]
                     calcul=calcul, source=plage.source), "", 2)  # type: ignore[attr-defined]


_CODE_REGLE_ALERTE = re.compile(r"^(C\d+)\b")


def _regles_coherence(element: Element, ctx: Contexte) -> list[_P]:
    """Regles C1-C17 et arithmetiques de la base qui concernent l'element (ok ou non)."""
    res: list[_P] = []
    for c in ctx.controles:
        if not concerne(c, element.texte):
            continue
        verdict = ("echec" if c.gravite == "bloquant" else "attention") if c.declenche else "ok"
        res.append(_P(Preuve(categorie="regle", verdict=verdict, titre=c.titre, detail=c.detail,  # type: ignore[arg-type]
                             calcul=c.calcul, source=c.source), c.detail if c.declenche else "", 3))
    deja = {p.preuve.titre for p in res}
    for a in ctx.alertes:
        if a.type != "incoherence" or element.id not in a.element_ids:
            continue
        m = _CODE_REGLE_ALERTE.match(a.message)
        if not m or any(a.message.startswith(c.code + " :") for c in ctx.controles):
            continue
        titre = f"Règle {m.group(1)}"
        if titre in deja:
            continue
        deja.add(titre)
        res.append(_P(Preuve(categorie="regle", verdict="echec" if a.gravite == "bloquant" else "attention", titre=titre,
                             detail=a.pourquoi or a.message, calcul=a.calcul, source=a.sources[0] if a.sources else None),
                      (a.pourquoi or a.message), 3))
    return res


# ---------------------------------------------------------------------------
# referentiel
# ---------------------------------------------------------------------------

_RANG_FIABILITE = {"A": 0, "B": 1, "C": 2, "D": 3}


def _champ_couvert(element: Element, ctx: Contexte) -> tuple[ChampAttendu | None, list[str]]:
    if element.champ_id:
        for c in ctx.champs:
            if c.id == element.champ_id:
                return c, []
    norm = normaliser(element.texte)
    meilleurs: list[tuple[int, ChampAttendu, list[str]]] = []
    for c in ctx.champs:
        mots = [normaliser(m).strip() for m in c.mots_cles]
        trouves = [m for m in mots if m and m not in _MOTS_CLES_GENERIQUES and len(m) >= 2 and contient_terme(norm, m)]
        if trouves:
            meilleurs.append((len(trouves), c, trouves))
    if not meilleurs:
        return None, []
    # plus de mots-cles, puis source la plus fiable (documents de l'utilisateur et officiels d'abord)
    meilleurs.sort(key=lambda x: (-x[0], _RANG_FIABILITE.get(x[1].fiabilite, 4)))
    _, champ, mots = meilleurs[0]
    return champ, mots


def _preuve_referentiel(element: Element, facteurs: list[conf_mod.Facteur], ctx: Contexte) -> _P:
    effet = round(sum(f.effet for f in facteurs if f.code == "fiabilite"), 4) or None
    champ, mots = _champ_couvert(element, ctx)
    if champ is None:
        return _P(Preuve(categorie="referentiel", verdict="info", titre="Champ du référentiel",
                         detail="Aucun champ obligatoire du référentiel ne porte sur cette phrase (contenu libre).",
                         effet=effet), "", 0, True)
    org = ctx.organe.libelle if ctx.organe else "cet organe"
    prel = {"biopsie": "une biopsie", "piece_operatoire": "une pièce opératoire", "cytologie": "une cytologie",
            "curage": "un curage"}.get(ctx.prelevement or "", "ce prélèvement")
    fia = champ.source.fiabilite if champ.source else None
    note = f" Source de fiabilité {fia} : à valider." if fia in ("C", "D") else ""
    detail = f"Renseigne « {champ.libelle} », champ obligatoire pour {org} sur {prel}." + note
    calcul = f"mots-clés retrouvés : {', '.join(mots[:4])}" if mots else None
    return _P(Preuve(categorie="referentiel", verdict="ok", titre="Champ du référentiel", detail=detail, calcul=calcul,
                     source=champ.source, effet=effet), "", 0, True)


# ---------------------------------------------------------------------------
# modele
# ---------------------------------------------------------------------------

def _termes_lexique(element: Element, ctx: Contexte) -> list[str]:
    """« adk » -> « adénocarcinome » : sigles dictes que l'element a normalises avec le lexique de la base."""
    norm_e, norm_d = normaliser(element.texte), normaliser(ctx.dictee)
    res: list[str] = []
    try:
        for e in ctx.ref._kb_appel("lexique", defaut=[]) or []:
            expansion = str(e.get("expansion") or "")
            terme = str(e.get("terme") or "")
            variantes = [str(v) for v in e.get("variantes") or [] if isinstance(v, str) and v.strip()]
            if terme and variantes and contient_terme(norm_e, normaliser(terme)) and not contient_terme(norm_d, normaliser(terme)):
                dictee_var = next((v for v in variantes if normaliser(v) != normaliser(terme) and contient_terme(norm_d, normaliser(v))), None)
                if dictee_var:  # variante de transcription dictee -> terme du lexique ecrit
                    res.append(f"« {dictee_var} » → « {terme} »")
                    if len(res) == 2:
                        break
                    continue
            if not expansion or not terme or normaliser(expansion) not in norm_e:
                continue
            sigles = [terme] + [str(v) for v in e.get("variantes") or [] if isinstance(v, str)]
            if normaliser(terme) in norm_e and normaliser(expansion) != normaliser(terme):
                continue
            if any(contient_terme(norm_d, normaliser(x)) for x in sigles if x.strip() and normaliser(x) != normaliser(expansion)):
                res.append(f"« {terme} » → « {expansion} »")
            if len(res) == 2:
                break
    except Exception:  # noqa: BLE001
        return res
    return res


_STATUT_TEXTE = {"dicte": "Dicté tel quel, sans reformulation.", "reformule": "Reformulé par le modèle de rédaction.",
                 "normalise": "Normalisé par le modèle de rédaction", "a_completer": "À compléter."}


def _preuve_modele(element: Element, facteurs: list[conf_mod.Facteur], verdict: "Verdict | None", relu: bool,
                   residu: float, residu_note: str, ctx: Contexte, note_relecteur: str = "") -> _P:
    statut = next((f for f in facteurs if f.code == "statut"), None)
    rel = next((f for f in facteurs if f.code == "relecteur"), None)
    morceaux = [_STATUT_TEXTE.get(element.statut, "")]
    if element.statut == "normalise":
        lex = _termes_lexique(element, ctx)
        morceaux[0] += (" : " + " ; ".join(lex) + " (lexique).") if lex else "."
    v = verdict.verdict if verdict else None
    if v == "fidele":
        morceaux.append("Relecteur indépendant : fidèle à la dictée.")
        verdict_p, raison = "ok", ""
    elif v == "doute":
        j = f" ({verdict.justification})" if verdict and verdict.justification else ""
        morceaux.append(f"Relecteur indépendant : doute{j}.")
        verdict_p, raison = "attention", f"Le relecteur doute de la fidélité à la dictée{j}."
    elif v in ("ajout", "contresens"):
        j = f" ({verdict.justification})" if verdict and verdict.justification else ""
        morceaux.append(f"Relecteur indépendant : {'ajout' if v == 'ajout' else 'contresens'} possible{j}.")
        verdict_p, raison = "echec", f"Le relecteur signale un possible {v}{j} : comparer à la dictée."
    elif note_relecteur:
        morceaux.append(note_relecteur[:1].upper() + note_relecteur[1:] + ".")
        verdict_p, raison = "info", ""
    else:
        morceaux.append("Relecteur indisponible pour cet élément.")
        verdict_p, raison = "attention", "La relecture par le second modèle n'a pas eu lieu : confiance abaissée."
    if element.statut == "reformule" and verdict_p == "ok":
        verdict_p = "info"
    effets = [f.effet for f in (statut, rel) if f is not None]
    total = round(sum(effets) + residu, 4)
    parts = []
    if statut:
        parts.append(f"{_fmt(statut.effet)} ({element.statut})")
    if rel:
        parts.append(f"{_fmt(rel.effet)} (relecteur)")
    if residu:
        parts.append(f"{_fmt(residu)} ({residu_note})")
        morceaux.append(residu_note[:1].upper() + residu_note[1:] + ".")
    calcul = (" ".join(parts) + f" = {_fmt(total)}") if parts else None
    src = SourceRef(kind="agent", ref="relecteur", libelle=f"Relecteur ({ctx.modele_relecteur})") if ctx.modele_relecteur else None
    return _P(Preuve(categorie="modele", verdict=verdict_p, titre="Ce que le modèle a fait",  # type: ignore[arg-type]
                     detail=" ".join(m for m in morceaux if m), calcul=calcul, source=src, effet=total), raison, 0, True)


# ---------------------------------------------------------------------------
# assemblage
# ---------------------------------------------------------------------------

def construire(element: Element, *, ancrage: str | None, verdict: "Verdict | None", relu: bool, confiance: float,
               ctx: Contexte, residu_note: str = "", note_relecteur: str = "") -> tuple[list[Preuve], str | None]:
    """Preuves ordonnees (3 a 6) et phrase ``a_verifier`` d'un element non-trou."""
    facteurs = conf_mod.decomposer(element, ancrage=ancrage, verdict=verdict.verdict if verdict else None,
                                   corrections=ctx.corrections, relecture_faite=relu)
    base = facteurs[0].effet
    somme = sum(f.effet for f in facteurs)
    # Confiance affichee = somme bornee a [0,05 ; 0,99], ou valeur imposee (passage repris tel quel, mode
    # degrade) : l'ecart eventuel est porte, avec sa raison, par la preuve du modele.
    residu = round(confiance - somme, 4)
    if abs(residu) < 0.006:  # simple arrondi a 2 decimales
        residu = 0.0
    elif not residu_note:
        residu_note = ("confiance bornée entre 5 % et 99 %" if conf_mod.borner(somme) != round(somme, 2)
                       else "ajustement de confiance du mode de traitement")

    obligatoires: list[_P] = [_preuve_dictee(element, ancrage, base, ctx)]
    ph = _preuve_phonetique(facteurs)
    if ph:
        obligatoires.append(ph)
    obligatoires.append(_preuve_referentiel(element, facteurs, ctx))
    obligatoires.append(_preuve_modele(element, facteurs, verdict, relu, residu, residu_note, ctx, note_relecteur))

    regles: list[_P] = []
    for fn in (_regle_chiffres, _regle_negations, _regle_plage):
        try:
            p = fn(element, ctx)
        except Exception:  # noqa: BLE001 - une regle fautive est ignoree, jamais bloquante
            p = None
        if p:
            regles.append(p)
    try:
        regles.extend(_regles_coherence(element, ctx))
    except Exception:  # noqa: BLE001
        pass
    # Place restante : les regles en echec ou attention d'abord, puis les regles satisfaites, dans l'ordre fixe.
    place = max(0, MAX_PREUVES - len(obligatoires))
    classees = sorted(regles, key=lambda p: (_GRAVITE_VERDICT[p.preuve.verdict], p.rang))
    gardees = sorted(classees[:place], key=lambda p: p.rang)
    toutes = obligatoires + gardees
    toutes.sort(key=lambda p: (_ORDRE_CATEGORIE[p.preuve.categorie], p.rang))
    preuves = [p.preuve for p in toutes]

    # a_verifier : la raison principale, regles avant jugement du modele.
    a_verifier: str | None = None
    regle_fautive = [p for p in toutes if p.preuve.categorie == "regle" and p.preuve.verdict in ("attention", "echec") and p.raison]
    niveau_bas = conf_mod.niveau_de(confiance) != "haute"
    if regle_fautive:
        regle_fautive.sort(key=lambda p: (_GRAVITE_VERDICT[p.preuve.verdict], p.rang))
        a_verifier = regle_fautive[0].raison
    elif niveau_bas:
        autres = [p for p in toutes if p.raison and p.preuve.verdict in ("attention", "echec")]
        autres.sort(key=lambda p: (_ORDRE_CATEGORIE[p.preuve.categorie] != 0, _GRAVITE_VERDICT[p.preuve.verdict], p.rang))
        if autres:
            a_verifier = autres[0].raison
        elif residu_note.startswith("passage dicté repris"):
            a_verifier = "Passage dicté repris tel quel après retrait de la rédaction : à mettre en forme."
        # Sans raison concrete (regle, relecteur, correction, ancrage), rien a signaler : pas de « à relire » vague.
    return preuves, a_verifier


# ---------------------------------------------------------------------------
# trous (champ obligatoire non dicte) : dictee -> regle -> referentiel, sans jugement du modele
# ---------------------------------------------------------------------------

_PRELEVEMENT_TXT = {"biopsie": "biopsie", "piece_operatoire": "pièce opératoire", "cytologie": "cytologie",
                    "curage": "curage", "extemporane": "examen extemporané"}
_LESION_DICTEE = re.compile(
    r"\b(?:carcinome|adénocarcinome|adenocarcinome|mélanome|melanome|lymphome|sarcome|tumeur|néoplasie|neoplasie)"
    r"\b[\w' -]{0,45}?(?=\s+(?:de grade|grade|stade|avec|sans|mesur|d'environ)\b|[.,;:()\n]|$)", re.I)
_CONTEXTE_TXT = {"malin": "lésion maligne", "benin": "lésion bénigne", "precancereux": "lésion précancéreuse",
                 "indetermine": "lésion de nature indéterminée", "indéterminé": "lésion de nature indéterminée"}


def _libelle_organe(champ: ChampAttendu, ctx: Contexte) -> str:
    if champ.organe_id in ("", "organe:generique"):
        return "tout organe"
    if ctx.organe and ctx.organe.id == champ.organe_id:
        return ctx.organe.libelle
    for o in ctx.ref._kb_appel("organes", defaut=[]) or []:
        if o.get("id") == champ.organe_id and o.get("libelle"):
            return str(o["libelle"])
    return champ.organe_id.split(":", 1)[-1].replace("_", " ")


def _lesion_dictee(ctx: Contexte) -> str:
    """Nature de la lesion telle que dictee (« carcinome canalaire infiltrant »), sinon le contexte detecte."""
    m = _LESION_DICTEE.search(ctx.dictee or "")
    if m:
        return " ".join(m.group(0).split()).lower()
    return _CONTEXTE_TXT.get(ctx.contexte or "", "")


def _termes_cherches(champ: ChampAttendu, ctx: Contexte) -> list[str]:
    """Mots-cles du champ puis variantes du lexique de la base qui leur correspondent (dedoublonnes)."""
    mots = [m for m in champ.mots_cles if m and normaliser(m).strip() not in _MOTS_CLES_GENERIQUES]
    vus: dict[str, str] = {}
    for m in mots:
        vus.setdefault(normaliser(m).strip(), m)
    cles = set(vus)
    try:
        for e in ctx.ref.lexique():
            formes = [e.terme] + [f for f, _ in e.variantes]
            if cles & {normaliser(f).strip() for f in formes}:
                for f in formes[:5]:
                    vus.setdefault(normaliser(f).strip(), f)
    except Exception:  # noqa: BLE001
        pass
    return list(vus.values())


def construire_trou(element: Element, ctx: Contexte) -> tuple[list[Preuve], str, str]:
    """(preuves ordonnees, a_verifier, explication) d'un trou, toujours dictee -> regle -> referentiel."""
    champ = next((c for c in ctx.champs if c.id == element.champ_id), None)
    lib = champ.libelle if champ else element.texte
    organe = _libelle_organe(champ, ctx) if champ else (ctx.organe.libelle if ctx.organe else "cet organe")
    prel = _PRELEVEMENT_TXT.get(ctx.prelevement or "", "")
    lesion = _lesion_dictee(ctx) if (champ is None or champ.tumoral) else ""
    pour = " · ".join(x for x in (organe.lower(), prel, lesion) if x)

    # 1. dictee : le champ n'est pas mentionne
    termes = _termes_cherches(champ, ctx) if champ else []
    if len(termes) > 10:
        txt_termes = ", ".join(termes[:10]) + " et d'autres variantes"
    else:
        txt_termes = ", ".join(termes)
    p_dictee = Preuve(
        categorie="dictee", verdict="info", titre="Mention dans la dictée",
        detail=f"« {lib} » n'est pas mentionné dans la dictée.",
        calcul=(f"0 mention trouvée pour : {txt_termes}" if txt_termes else "0 mention trouvée"),
        source=None, effet=None)

    # 2. regle : la condition reelle qui a declenche l'exigence
    conditions = [f"organe = {organe.lower()}"]
    if prel:
        conditions.append(f"prélèvement = {prel}")
    if champ is not None and champ.tumoral:
        conditions.append("champ tumoral : exigé quand la lésion est maligne")
        if ctx.contexte:
            conditions.append(f"lésion détectée = {_CONTEXTE_TXT.get(ctx.contexte, ctx.contexte)}")
    elif champ is not None:
        conditions.append("champ non tumoral : exigé quelle que soit la nature de la lésion")
    if champ is not None and champ.condition:
        conditions.append(f"condition de la source : {champ.condition}")
    p_regle = Preuve(
        categorie="regle", verdict="info", titre="Pourquoi ce champ est exigé ici",
        detail=f"Exigé pour : {pour}.", calcul=" ; ".join(conditions), source=None, effet=None)

    # 3. referentiel : la source reelle, avec sa localisation exacte
    src = champ.source_exigence if champ else (element.sources[0] if element.sources else None)
    inca = champ is not None and champ.source_inca is not None
    if inca:
        detail_ref = f"Donnée minimale du référentiel INCa/SFP pour {organe.lower()} : « {lib} »."
    else:
        detail_ref = (f"Exigence du gabarit interne MARC pour {organe.lower()} : « {lib} » ne figure pas "
                      f"dans les données minimales INCa chargées ; à faire valider par la pathologiste référente.")
    fia = src.fiabilite if src else None
    if inca and fia in ("C", "D"):
        detail_ref += f" Source de fiabilité {fia} : à valider."
    p_ref = Preuve(categorie="referentiel", verdict="info", titre="Source du champ", detail=detail_ref,
                   calcul=None, source=src, effet=None)

    if inca:
        phrase = f"« {lib} » fait partie des données minimales INCa pour {pour} ; il n'a pas été dicté."
    else:
        phrase = (f"« {lib} » est exigé par le gabarit interne MARC pour {pour} (à valider par la pathologiste) ; "
                  f"il n'a pas été dicté.")
    return [p_dictee, p_regle, p_ref], phrase, phrase
