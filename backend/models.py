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
