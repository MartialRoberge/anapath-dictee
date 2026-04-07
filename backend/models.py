"""Modèles Pydantic partagés pour l'API Anapath."""

from pydantic import BaseModel


class TranscriptionResponse(BaseModel):
    """Réponse de transcription audio."""

    raw_transcription: str


class FormatRequest(BaseModel):
    """Requête de mise en forme d'un transcript."""

    raw_text: str
    rapport_precedent: str = ""


class DonneeManquante(BaseModel):
    """Donnée obligatoire manquante dans le compte-rendu."""

    champ: str
    description: str
    section: str
    obligatoire: bool = True


class FormatResponse(BaseModel):
    """Réponse de mise en forme avec détection des données manquantes."""

    formatted_report: str
    organe_detecte: str
    donnees_manquantes: list[DonneeManquante]


class IterationRequest(BaseModel):
    """Requête d'itération sur un compte-rendu existant."""

    rapport_actuel: str
    nouveau_transcript: str


class IterationResponse(BaseModel):
    """Réponse d'itération avec mise à jour du compte-rendu."""

    formatted_report: str
    organe_detecte: str
    donnees_manquantes: list[DonneeManquante]


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


class SnomedCode(BaseModel):
    """Un code SNOMED CT."""

    code: str
    display: str
    system: str


class SnomedResponse(BaseModel):
    """Reponse avec les codes SNOMED CT suggeres."""

    topography: SnomedCode
    morphology: SnomedCode


class CompletudeRequest(BaseModel):
    """Requête de calcul du score de complétude INCa."""

    formatted_report: str
    organe_detecte: str


class CompletudeResponse(BaseModel):
    """Réponse avec le score de complétude INCa."""

    score: int
    total_champs: int
    champs_presents: int
    pourcentage: float
