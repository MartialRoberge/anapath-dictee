"""Modèles Pydantic partagés pour l'API Anapath."""

from pydantic import BaseModel


class TranscriptionResponse(BaseModel):
    """Réponse de transcription audio."""

    raw_transcription: str


class FormatRequest(BaseModel):
    """Requête de mise en forme d'un transcript.

    La génération est entièrement automatique : aucun template à choisir.
    """

    raw_text: str
    rapport_precedent: str = ""


class DonneeManquante(BaseModel):
    """Donnée obligatoire manquante dans le compte-rendu."""

    champ: str
    description: str
    section: str
    obligatoire: bool = True


class CoherenceIssue(BaseModel):
    """Un probleme de coherence medicale detecte dans le compte-rendu."""

    code: str
    message: str
    severity: str  # "bloquant" | "attention"


class CoherenceVerdict(BaseModel):
    """Verdict de coherence medicale (structure + coherence interne)."""

    ok: bool = True
    structure_complete: bool = True
    sections_presentes: list[str] = []
    issues: list[CoherenceIssue] = []


class FormatResponse(BaseModel):
    """Réponse de mise en forme avec détection des données manquantes."""

    formatted_report: str
    organe_detecte: str
    donnees_manquantes: list[DonneeManquante]
    # Champs additifs (retrocompatibles) : garde-fous + traçabilité auto-détection.
    warnings: list[str] = []
    organes_detectes: list[str] = []
    type_prelevement: str = "autre"
    # Verdict de coherence medicale calcule a chaque generation.
    coherence: CoherenceVerdict = CoherenceVerdict()


class IterationRequest(BaseModel):
    """Requête d'itération sur un compte-rendu existant."""

    rapport_actuel: str
    nouveau_transcript: str


class IterationResponse(FormatResponse):
    """Réponse d'itération : contrat identique à la mise en forme initiale.

    L'itération produit le meme objet qu'une generation (CR + panneau + garde-fous
    + coherence) ; elle herite donc de FormatResponse pour garantir un seul contrat.
    """


class ExportRequest(BaseModel):
    """Requête d'export Word."""

    formatted_report: str
    title: str = "Compte-rendu anatomopathologique"


class SectionsResponse(BaseModel):
    """Réponse avec le compte-rendu découpé en sections."""

    sections: dict[str, str]


class AdicapRequest(BaseModel):
    """Requête de suggestion de code ADICAP."""

    formatted_report: str
    organe_detecte: str


class AdicapResponse(BaseModel):
    """Réponse avec le code ADICAP suggéré."""

    code: str
    prelevement: str
    prelevement_code: str
    technique: str
    technique_code: str
    organe: str
    organe_code: str
    lesion: str
    lesion_code: str
    # Traçabilité de confiance : "haute" (code lésionnel validé),
    # "organe_seul" (lésion différée), "aucune".
    confidence: str = "haute"
    note: str = ""


class SnomedCode(BaseModel):
    """Un code SNOMED CT."""

    code: str
    display: str
    system: str


class SnomedResponse(BaseModel):
    """Reponse avec les codes SNOMED CT suggeres."""

    topography: SnomedCode
    morphology: SnomedCode


