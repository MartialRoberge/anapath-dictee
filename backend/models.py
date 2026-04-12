"""Modeles Pydantic pour l'API Anapath v4.

Les schemas internes du pipeline (CRDocument, Classification, Marker...)
sont dans ``schemas.py``. Ce fichier ne contient que les models publics
des endpoints HTTP.
"""

from pydantic import BaseModel

from schemas import Classification, CRDocument, Marker


class TranscriptionResponse(BaseModel):
    """Reponse de transcription audio (endpoint /transcribe)."""

    raw_transcription: str


class FormatRequest(BaseModel):
    """Requete /format : transcript a structurer."""

    raw_text: str


class FormatResponse(BaseModel):
    """Reponse /format v4 : CR rendu + document structure + markers typed."""

    trace_id: str
    formatted_report: str
    document: CRDocument
    classification: Classification
    markers: list[Marker]


class IterationRequest(BaseModel):
    """Requete /iterate : ajouter une dictee complementaire a un rapport."""

    rapport_actuel: str
    nouveau_transcript: str


class IterationResponse(BaseModel):
    """Reponse /iterate (meme structure que FormatResponse)."""

    trace_id: str
    formatted_report: str
    document: CRDocument
    classification: Classification
    markers: list[Marker]


class ExportRequest(BaseModel):
    """Requete /export Word."""

    formatted_report: str
    title: str = "Compte-rendu anatomopathologique"
