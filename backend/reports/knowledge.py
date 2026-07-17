"""Injection AUTOMATIQUE de connaissances metier, multi-organes.

Principe (exigence produit) : l'anatomopathologiste NE choisit JAMAIS de template.
Il dicte, le compte-rendu sort. La structure est portee par le prompt de base
(deja multi-prelevement) ; ce module y ajoute, de facon ADDITIVE, les connaissances
propres a CHAQUE organe detecte dans la dictee.

Un meme prelevement peut concerner plusieurs organes/sites (piece pulmonaire +
curage ganglionnaire, biopsies etagees oesophage/estomac/duodenum, ...). On detecte
donc TOUS les organes presents et on injecte le pack de chacun — jamais un template
unique impose.

Source : ``templates_organes`` (23 organes, champs INCa, classifications, panels IHC).
Base de connaissances non ecrite a partir des cas de test -> non biaisee.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from functools import lru_cache

from specimen_type import (
    DiagnosticContext,
    SpecimenType,
    champ_applicable,
    detecter_diagnostic_context,
    detecter_specimen_type,
)
from templates_organes import TOUS_LES_TEMPLATES, TemplateOrgane

# Nombre max d'organes injectes (au-dela, on reste generique pour ne pas noyer
# le prompt ; en pratique un CR concerne 1 a 3 organes/sites).
_MAX_ORGANS: int = 4

# Mots-cles GENERIQUES/partages entre organes : ne doivent JAMAIS declencher a eux
# seuls la detection d'un organe (sinon "curage ganglionnaire" d'une piece
# pulmonaire ferait croire a un lymphome, "lobectomie" a un foie, etc.).
# Un organe n'est retenu que s'il matche au moins un mot-cle SPECIFIQUE.
_WEAK_KEYWORDS: frozenset[str] = frozenset(
    {
        "ganglion", "ganglions", "ganglionnaire", "ganglionnaires",
        "lobe", "lobectomie", "adenocarcinome", "adénocarcinome",
        "carcinome", "biopsie", "biopsies", "tumeur", "tumoral", "tumorale",
        "nodule", "masse", "kyste", "polype", "resection", "résection",
        "piece", "pièce", "cellules", "lesion", "lésion",
        # Ambigus cou/col-uterin : "adenopathie cervicale" = ganglion du cou,
        # ne doit pas declencher col uterin ni ORL a lui seul.
        "cervical", "cervicale",
        # Le "hile" existe au poumon, foie, rein, rate... : non discriminant seul
        # (evitait un faux "poumon" sur un cholangiocarcinome "hilaire").
        "hilaire", "hile", "hilaires",
    }
)


@lru_cache(maxsize=1)
def _keyword_patterns() -> list[tuple[TemplateOrgane, list[tuple[str, re.Pattern[str]]]]]:
    """Precompile les regex a limites de mots pour chaque mot-cle d'organe."""
    compiled: list[tuple[TemplateOrgane, list[tuple[str, re.Pattern[str]]]]] = []
    for tpl in TOUS_LES_TEMPLATES:
        pats: list[tuple[str, re.Pattern[str]]] = []
        for kw in tpl.mots_cles_detection:
            # Pluriel francais tolere (-s / -x) : "biopsies COLIQUES" doit matcher
            # le mot-cle "colique", "vaisseaux" -> "vaisseau". Les limites de mots
            # restent strictes (pas de "CIN" dans "adenocarCINome").
            pat = re.compile(rf"\b{re.escape(kw.lower())}(?:s|x)?\b")
            pats.append((kw.lower(), pat))
        compiled.append((tpl, pats))
    return compiled


@dataclass(slots=True)
class ContextResult:
    """Bloc de contexte metier + organes detectes."""

    block: str
    organes: list[str] = field(default_factory=list)
    specimen: SpecimenType = SpecimenType.INDETERMINE
    diagnostic: DiagnosticContext = DiagnosticContext.INDETERMINE


def detect_organs(transcript: str) -> list[TemplateOrgane]:
    """Detecte TOUS les organes presents dans la dictee, ordonnes par pertinence.

    Multi-organes : renvoie une liste (potentiellement vide). Robuste :
    * correspondance sur limites de mots (evite "CIN" dans "adenocarCINome") ;
    * un organe n'est retenu que s'il matche >=1 mot-cle SPECIFIQUE (non generique),
      pour eviter qu'un terme partage ("ganglion", "lobectomie") ne cree un faux
      organe et donc une classification hors contexte.
    """
    text: str = transcript.lower()
    scored: list[tuple[int, TemplateOrgane]] = []
    for tpl, pats in _keyword_patterns():
        matched: list[str] = [kw for kw, pat in pats if pat.search(text)]
        if not matched:
            continue
        has_specific: bool = any(kw not in _WEAK_KEYWORDS for kw in matched)
        if not has_specific:
            continue
        scored.append((len(matched), tpl))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [tpl for _, tpl in scored[:_MAX_ORGANS]]


def _organ_block(
    tpl: TemplateOrgane, specimen: SpecimenType, contexte: DiagnosticContext
) -> str:
    """Construit le bloc de connaissances concis d'un organe (guide, non rigide)."""
    champs = [
        c.nom
        for c in tpl.champs_obligatoires
        if champ_applicable(c.nom, specimen, contexte)
    ]
    lines: list[str] = [f"── Organe detecte : {tpl.nom_affichage} ──"]
    if champs:
        lines.append(
            "Champs pertinents attendus (UNIQUEMENT si dictes ; sinon "
            "[A COMPLETER: ...], jamais inventes) : " + " ; ".join(champs)
        )
    if tpl.systeme_staging:
        lines.append(f"Classification applicable a cet organe : {tpl.systeme_staging}")
    if tpl.marqueurs_ihc:
        lines.append(
            "Panel IHC usuel (si des marqueurs sont dictes) : "
            + ", ".join(tpl.marqueurs_ihc[:8])
        )
    if tpl.notes_specifiques:
        note = tpl.notes_specifiques.strip().replace("\n", " ")
        lines.append(f"Note : {note[:400]}")
    return "\n".join(lines)


def build_context_block(transcript: str) -> ContextResult:
    """Assemble le bloc de contexte metier automatique pour une dictee.

    Ne force aucune structure : fournit, par organe detecte, les champs attendus
    et la classification APPLICABLE A CET ORGANE (pour eviter d'appliquer une
    classification d'un autre organe). Multi-organes gere nativement.
    """
    specimen: SpecimenType = detecter_specimen_type(transcript)
    contexte: DiagnosticContext = detecter_diagnostic_context(transcript)
    organs: list[TemplateOrgane] = detect_organs(transcript)

    if not organs:
        # Aucun organe reconnu : on laisse le prompt de base gerer entierement.
        return ContextResult(
            block="", organes=[], specimen=specimen, diagnostic=contexte
        )

    parts: list[str] = ["════════ CONTEXTE METIER (detecte automatiquement) ════════"]
    if len(organs) > 1:
        noms = ", ".join(o.nom_affichage for o in organs)
        parts.append(
            f"PLUSIEURS ORGANES/SITES detectes ({noms}). Traite CHAQUE prelevement "
            "dans sa propre section numerotee, avec ses propres champs et sa propre "
            "classification. N'applique jamais la classification d'un organe a un autre."
        )
    parts.append(
        "Applique la connaissance ci-dessous UNIQUEMENT si la dictee la concerne. "
        "N'ajoute aucun champ non dicte (au pire [A COMPLETER: ...])."
    )
    for tpl in organs:
        parts.append("")
        parts.append(_organ_block(tpl, specimen, contexte))

    # Formulation de REFERENCE du praticien pour la lesion dictee (sa propre
    # bible) : donne le vocabulaire, la structure et la densite qu'IL attend.
    # Verrouille par organe ; vide si la lesion n'est pas dans sa bible.
    from reports.canonical_texts import build_canonical_block

    canonical = build_canonical_block(transcript, [o.organe for o in organs])
    if canonical:
        parts.append("")
        parts.append(canonical)

    return ContextResult(
        block="\n".join(parts),
        organes=[o.organe for o in organs],
        specimen=specimen,
        diagnostic=contexte,
    )
