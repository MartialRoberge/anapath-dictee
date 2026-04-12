"""Schemas Pydantic du pipeline v4 Anapath.

Contrat central entre les etapes du workflow : classification, regles,
retrieval, generation LLM, validation, rendu. Tout objet echange entre
modules metier passe par ces types, jamais par des dicts bruts.

Convention : un seul concept par classe, nom au singulier, docstring qui
explique le role de l'objet dans le pipeline (pas son contenu, qui est
auto-documente par les champs).
"""

from typing import Literal

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Classification (sortie de l'etape 2)
# ---------------------------------------------------------------------------


Organe = Literal[
    "poumon",
    "sein",
    "digestif",
    "gynecologie",
    "urologie",
    "orl",
    "dermatologie",
    "hematologie",
    "os_articulations",
    "tissus_mous",
    "neurologie",
    "ophtalmologie",
    "cardiovasculaire",
    "endocrinologie",
    "generic",
]


class ClassificationCandidate(BaseModel):
    """Un candidat d'identification du prelevement propose par Claude.

    L'etape 2 retourne top-2 candidats pour permettre un fallback gracieux
    si la confidence du meilleur est trop basse.
    """

    organe: Organe
    sous_type: str
    est_carcinologique: bool
    diagnostic_presume: str
    confidence: float = Field(ge=0.0, le=1.0)


class Classification(BaseModel):
    """Resultat complet de l'etape 2 : top-2 candidats + metadonnees.

    Le pipeline aval utilise ``top.organe`` + ``top.sous_type`` pour
    charger les regles et filtrer le retrieval. Si ``top.confidence < 0.7``,
    fallback sur le ruleset ``generic``.
    """

    top: ClassificationCandidate
    alternative: ClassificationCandidate | None = None
    transcript_normalise: str
    confidence_threshold: float = 0.7

    @property
    def needs_fallback(self) -> bool:
        """True si la confidence est trop basse pour appliquer les regles specifiques."""
        return self.top.confidence < self.confidence_threshold


# ---------------------------------------------------------------------------
# Regles metier (etape 3, chargees depuis YAML)
# ---------------------------------------------------------------------------


class ChampObligatoire(BaseModel):
    """Un champ obligatoire pour un (organe, sous-type) donne.

    ``conditions`` est une liste de tokens declaratifs que les validateurs
    Python interpretent. Exemple : ``["tumoral", "adenocarcinome"]`` signifie
    "obligatoire si le contexte est tumoral ET qu'il s'agit d'un adenocarcinome".
    """

    nom: str
    section: Literal[
        "titre",
        "renseignements_cliniques",
        "macroscopie",
        "microscopie",
        "immunomarquage",
        "biologie_moleculaire",
        "conclusion",
    ]
    conditions: list[str] = Field(default_factory=list)
    description: str = ""


class SousTypeRules(BaseModel):
    """Regles applicables a un sous-type de prelevement pour un organe.

    Exemples de sous-types poumon : ``biopsie_bronchique``, ``piece_operatoire``,
    ``lba``, ``ebus``, ``aspiration_bronchique``, ``transthoracique``.
    """

    nom: str
    mots_cles_detection: list[str] = Field(default_factory=list)
    champs_obligatoires: list[ChampObligatoire] = Field(default_factory=list)
    marqueurs_ihc_attendus: list[str] = Field(default_factory=list)
    template_macroscopie: str = ""
    notes: str = ""


class OrganRules(BaseModel):
    """Ensemble complet des regles pour un organe (charge depuis YAML)."""

    organe: Organe
    nom_affichage: str
    sous_types: dict[str, SousTypeRules]
    systeme_staging: str = ""
    description: str = ""


# ---------------------------------------------------------------------------
# Retrieval (etape 4)
# ---------------------------------------------------------------------------


class BiblesEntry(BaseModel):
    """Une entree de la table structuree Bibles Greg.xlsx.

    Chaque ligne des feuilles (DIG, THO, URO, ...) produit une entree :
    (organe, sous-topographie, lesion, code ADICAP, texte standard).
    """

    organe: Organe
    topographie: str
    lesion: str
    code_adicap: str
    texte_standard: str
    feuille_source: str


class ExampleCR(BaseModel):
    """Un CR exemple issu du dossier Modeles CR, utilise par le RAG de style."""

    filename: str
    organe: Organe
    sous_type_guess: str
    titre: str
    full_text: str
    section_conclusion: str
    diagnostic_keywords: list[str]


class RetrievalResult(BaseModel):
    """Resultat complet de l'etape 4 : exemples + entrees bibles pertinentes."""

    exemples_cr: list[ExampleCR]
    entrees_bibles: list[BiblesEntry]


# ---------------------------------------------------------------------------
# CR Document structure (sortie de l'etape 5, entree de l'etape 7)
# ---------------------------------------------------------------------------


class IhcRow(BaseModel):
    """Une ligne du tableau d'immunomarquage.

    La colonne ``temoin`` est optionnelle et ne doit etre renseignee que
    si le pathologiste l'a explicitement dictee. Par defaut elle est vide
    et le rendu Jinja n'affichera pas la colonne.
    """

    anticorps: str
    resultat: str
    temoin: str = ""


class IhcTable(BaseModel):
    """Tableau d'immunomarquage complet.

    Le rendu n'ajoute la colonne ``Temoin +`` au markdown final que si
    au moins une ligne a un ``temoin`` non vide. Elimination par
    construction du bug "colonne temoin toujours presente".
    """

    phrase_introduction: str = ""
    lignes: list[IhcRow] = Field(default_factory=list)

    @property
    def has_temoin_column(self) -> bool:
        """True si au moins une ligne a une valeur temoin non vide."""
        return any(row.temoin.strip() for row in self.lignes)


class Prelevement(BaseModel):
    """Un prelevement distinct dans un CR multi-prelevement.

    Un CR a au moins un prelevement. Pour un CR simple, la liste
    ``CRDocument.prelevements`` contient un seul element dont ``numero``
    vaut 1 et ``titre_court`` est vide.
    """

    numero: int
    titre_court: str = ""
    macroscopie: str = ""
    microscopie: str = ""
    immunomarquage: IhcTable | None = None
    biologie_moleculaire: str = ""


class CRDocument(BaseModel):
    """Le compte-rendu structure produit par Claude (JSON mode).

    Cet objet est la source de verite pour le rendu markdown final. Le
    LLM ne produit JAMAIS de markdown directement. Le rendu deterministe
    Jinja garantit la presence des titres "Macroscopie", "Microscopie",
    "Conclusion" et gere l'affichage conditionnel des sections vides.
    """

    titre: str
    renseignements_cliniques: str = ""
    prelevements: list[Prelevement]
    conclusion: str
    ptnm: str = ""
    commentaire_final: str = ""
    code_adicap: str = ""
    codes_snomed: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Validation (etape 6)
# ---------------------------------------------------------------------------


class Marker(BaseModel):
    """Un marqueur de champ manquant ou auto-complete dans le CR final.

    Les markers remplacent la detection regex de la v3. Ils sont emis par
    les validateurs Python en comparant ``CRDocument`` aux ``OrganRules``.
    Le frontend consomme ces objets directement pour rendre des chips
    interactifs : plus de regex sur la prose cote client.
    """

    field: str
    section: Literal[
        "titre",
        "renseignements_cliniques",
        "macroscopie",
        "microscopie",
        "immunomarquage",
        "biologie_moleculaire",
        "conclusion",
    ]
    rule_id: str
    severity: Literal["error", "warning", "info"]
    message: str
    auto_filled: bool = False
    auto_filled_value: str = ""


class ValidationResult(BaseModel):
    """Sortie de l'etape 6 : le CRDocument eventuellement modifie + les markers."""

    document: CRDocument
    markers: list[Marker]


# ---------------------------------------------------------------------------
# Observabilite : trace_id pour rejouer un pipeline
# ---------------------------------------------------------------------------


class AgentTraceStep(BaseModel):
    """Une etape tracee du pipeline, persistee pour audit et replay."""

    step_name: Literal[
        "transcribe",
        "corriger_phonetique",
        "classify",
        "load_rules",
        "retrieve",
        "generate",
        "validate",
        "render",
    ]
    duration_ms: int
    input_summary: str
    output_summary: str


class AgentTrace(BaseModel):
    """Trace complete d'une invocation du pipeline pour un report.

    Permet a un admin de rejouer exactement pourquoi un CR a ete mal
    structure : classification, regles chargees, exemples retrouves,
    sortie brute de Claude, resultat de validation.
    """

    trace_id: str
    report_id: int | None
    steps: list[AgentTraceStep]
    classification: Classification | None = None
    markers: list[Marker] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# API Response v4 (remplace FormatResponse de la v3)
# ---------------------------------------------------------------------------


class FormatResponseV4(BaseModel):
    """Reponse enrichie du endpoint /format en v4.

    Inclut le CRDocument structure, le markdown rendu, les markers typed
    et le trace_id pour permettre au frontend d'afficher des chips
    interactifs et a l'admin d'auditer le pipeline.
    """

    trace_id: str
    formatted_report: str
    document: CRDocument
    classification: Classification
    markers: list[Marker]
