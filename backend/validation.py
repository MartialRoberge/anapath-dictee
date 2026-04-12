"""Etape 6 du pipeline v4 : validation du CRDocument contre les regles.

Compare le CRDocument produit par Claude aux regles YAML de l'organe
detecte et emet des Marker pour chaque champ obligatoire absent ou mal
rempli.

Philosophie : l'evaluation est *declarative*. Les regles YAML declarent
des champs avec des conditions (ex: ``[carcinologique]``), ce module
les interprete contre la Classification et le CRDocument pour decider
si le champ est applicable et present.

Les predicats conditionnels specifiques a un organe (ex: "grade ISUP
non applicable au chromophobe") vivent dans ``rules/validators/<organe>.py``
pour que le cas general reste trivial.
"""

from __future__ import annotations

from schemas import (
    ChampObligatoire,
    Classification,
    CRDocument,
    Marker,
    OrganRules,
    SousTypeRules,
    ValidationResult,
)
from text_utils import strip_accents


def _collect_section_text(doc: CRDocument, section: str) -> str:
    """Concatene tout le texte libre d'une section pour detection mot-cle."""
    parts: list[str] = []

    if section == "titre":
        parts.append(doc.titre)
    elif section == "renseignements_cliniques":
        parts.append(doc.renseignements_cliniques)
    elif section == "conclusion":
        parts.append(doc.conclusion)
        parts.append(doc.ptnm)
    else:
        for prel in doc.prelevements:
            if section == "macroscopie":
                parts.append(prel.macroscopie)
            elif section == "microscopie":
                parts.append(prel.microscopie)
            elif section == "biologie_moleculaire":
                parts.append(prel.biologie_moleculaire)
            elif section == "immunomarquage":
                if prel.immunomarquage is not None:
                    for row in prel.immunomarquage.lignes:
                        parts.append(f"{row.anticorps} {row.resultat}")

    return strip_accents(" ".join(p for p in parts if p).lower())


# ---------------------------------------------------------------------------
# Evaluation des conditions
# ---------------------------------------------------------------------------


_DIAGNOSTIC_SYNONYMS: dict[str, list[str]] = {
    "adenocarcinome": ["adenocarcinome", "adk"],
    "carcinome_epidermoide": [
        "carcinome epidermoide", "carcinome epi", "ce ",
        "squameux", "spinocellulaire",
    ],
    "medicale": ["glomerul", "biopsie medicale", "nephropath"],
}


def _matches_condition(
    condition: str, classification: Classification
) -> bool:
    """Indique si une condition declarative est verifiee.

    Conditions actuellement supportees :
    - ``carcinologique`` : Classification.top.est_carcinologique == True
    - ``adenocarcinome`` : diagnostic_presume contient un synonyme
    - ``carcinome_epidermoide`` : idem
    - ``medicale`` : idem
    """
    top = classification.top

    if condition == "carcinologique":
        return top.est_carcinologique

    diag_norm: str = strip_accents(top.diagnostic_presume.lower())
    synonyms: list[str] = _DIAGNOSTIC_SYNONYMS.get(condition, [condition])
    return any(strip_accents(syn.lower()) in diag_norm for syn in synonyms)


def _champ_applicable(
    champ: ChampObligatoire, classification: Classification
) -> bool:
    """Un champ est applicable si toutes ses conditions sont remplies."""
    return all(_matches_condition(cond, classification) for cond in champ.conditions)


# ---------------------------------------------------------------------------
# Detection de presence d'un champ dans le document
# ---------------------------------------------------------------------------


def _champ_est_present(champ: ChampObligatoire, doc: CRDocument) -> bool:
    """Detecte si un champ obligatoire est effectivement renseigne.

    Heuristique :
    1. Si le nom du champ contient un token specifique (ex: "pTNM",
       "TTF1", "taille"), on cherche ce token dans la section concernee.
    2. Sinon, on considere que le champ est present des que la section
       n'est pas vide.
    """
    section_text: str = _collect_section_text(doc, champ.section)
    if not section_text:
        return False

    specific_tokens: list[str] = _extract_specific_tokens(champ.nom)
    if not specific_tokens:
        return len(section_text) > 10

    for token in specific_tokens:
        if strip_accents(token) in section_text:
            return True
    return False


# Seuls les champs a vocabulaire fini utilisent un token specifique.
# Les champs semantiques (type histologique, description macro...) sont
# valides par simple presence de contenu dans la section.
_SPECIFIC_TOKEN_MAP: dict[str, list[str]] = {
    "pTNM": ["ptnm", "pt1", "pt2", "pt3", "pt4", "pn0", "pn1", "pn2"],
    "TTF1": ["ttf1", "ttf-1"],
    "p40": ["p40"],
    "PD-L1": ["pd-l1", "pdl1", "pd l1"],
    "ALK": ["alk"],
    "ROS1": ["ros1", "ros-1"],
    "Score de Gleason": ["gleason"],
    "ISUP grade group": ["isup", "grade group"],
    "Grade nucleaire ISUP": ["isup", "grade"],
    "Marges de resection": ["marge", "limite", "recoupe"],
    "Ganglions envahis / examines": ["ganglion", "curage"],
    "Emboles vasculaires": ["embole", "invasion vasculaire"],
    "Engainements perinerveux": ["engainement", "perinerveux"],
    "Invasion pleurale viscerale": ["pleurale", "pl0", "pl1", "pl2", "pl3"],
    "Invasion graisse sinusale": ["graisse sinus", "sinus"],
    "Invasion graisse perirenale (capsule de Gerota)": ["gerota", "perirenal", "capsule"],
    "Invasion veine renale": ["veine renale", "vasculaire"],
}


def _extract_specific_tokens(nom_champ: str) -> list[str]:
    """Retourne les tokens significatifs pour le nom d'un champ donne."""
    for key, tokens in _SPECIFIC_TOKEN_MAP.items():
        if strip_accents(key.lower()) in strip_accents(nom_champ.lower()):
            return tokens
    return []


# ---------------------------------------------------------------------------
# Validation principale
# ---------------------------------------------------------------------------


def _pick_sous_type_rules(
    rules: OrganRules, sous_type_key: str
) -> SousTypeRules | None:
    """Retourne les regles pour le sous-type identifie, ou None s'il n'existe pas."""
    return rules.sous_types.get(sous_type_key)


def _build_marker(
    champ: ChampObligatoire, organe: str, sous_type_key: str
) -> Marker:
    """Construit un Marker pour un champ manquant."""
    severity: str = "error" if not champ.conditions else "warning"
    return Marker(
        field=champ.nom,
        section=champ.section,
        rule_id=f"{organe}.{sous_type_key}.{_slugify(champ.nom)}",
        severity=severity,  # type: ignore[arg-type]
        message=champ.description or f"Champ obligatoire manquant : {champ.nom}",
        auto_filled=False,
        auto_filled_value="",
    )


def _slugify(text: str) -> str:
    """Version minimale pour rule_id."""
    out: str = strip_accents(text)
    allowed: list[str] = []
    for c in out:
        if c.isalnum():
            allowed.append(c)
        elif c in " -_":
            allowed.append("_")
    return "".join(allowed).strip("_")


def validate_cr(
    doc: CRDocument,
    classification: Classification,
    rules: OrganRules,
) -> ValidationResult:
    """Valide un CRDocument contre les regles de l'organe.

    Point d'entree de l'etape 6. Retourne le document eventuellement
    amende (reserve pour l'autocompletion future) et la liste des
    markers pour le frontend.
    """
    markers: list[Marker] = []
    sous_type_key: str = classification.top.sous_type
    sous_type_rules: SousTypeRules | None = _pick_sous_type_rules(rules, sous_type_key)

    if sous_type_rules is None:
        # Fallback sur le premier sous-type disponible (ruleset generique)
        if rules.sous_types:
            sous_type_key = next(iter(rules.sous_types))
            sous_type_rules = rules.sous_types[sous_type_key]
        else:
            return ValidationResult(document=doc, markers=[])

    for champ in sous_type_rules.champs_obligatoires:
        if not _champ_applicable(champ, classification):
            continue
        if _champ_est_present(champ, doc):
            continue
        markers.append(_build_marker(champ, rules.organe, sous_type_key))

    return ValidationResult(document=doc, markers=markers)
