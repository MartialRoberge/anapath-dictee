"""API FastAPI pour l'application de dictee anatomopathologique.

Endpoints :
- POST /transcribe   : Transcription audio via Voxtral
- POST /format       : Mise en forme du transcript en compte-rendu structure
- POST /iterate      : Ajout d'une dictee complementaire a un rapport existant
- POST /sections     : Decoupage d'un rapport en sections nommees
- POST /export       : Export du compte-rendu en .docx
- GET  /health       : Verification du statut de l'API

Note proxy frontend : le frontend doit proxifier /transcribe, /format,
/iterate, /sections et /export vers ce backend.
"""

import io
from pathlib import Path

import httpx
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from models import (
    TranscriptionResponse,
    FormatRequest,
    FormatResponse,
    IterationRequest,
    IterationResponse,
    ExportRequest,
    SectionsResponse,
    DonneeManquante,
)
from transcription import transcribe_audio
from formatting import format_transcription, iterer_rapport
from export_docx import markdown_to_docx, split_report_sections
from detection_manquantes import detecter_donnees_manquantes

app: FastAPI = FastAPI(title="Anapath - Dictee medicale", version="0.4.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------


@app.get("/health")
async def health() -> dict[str, str]:
    """Verification du statut de l'API."""
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# Transcription audio
# ---------------------------------------------------------------------------


ALLOWED_AUDIO_PREFIXES: list[str] = ["audio/", "video/"]
ALLOWED_EXTENSIONS: set[str] = {
    ".webm", ".mp3", ".mp4", ".m4a", ".mov", ".wav", ".ogg", ".flac", ".aac",
}


@app.post("/transcribe", response_model=TranscriptionResponse)
async def transcribe(file: UploadFile = File(...)) -> TranscriptionResponse:
    """Etape 1 : Transcription audio via Voxtral.

    Accepte les formats : webm, mp3, mp4, m4a, mov, wav, ogg, flac, aac.
    """
    content_type: str = file.content_type or ""
    filename: str = file.filename or "recording.webm"
    ext: str = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""

    type_ok: bool = any(content_type.startswith(p) for p in ALLOWED_AUDIO_PREFIXES)
    ext_ok: bool = ext in ALLOWED_EXTENSIONS

    if not type_ok and not ext_ok:
        raise HTTPException(
            status_code=400,
            detail=f"Format non supporte ({content_type}, {ext}). "
            f"Formats acceptes : {', '.join(sorted(ALLOWED_EXTENSIONS))}",
        )

    audio_bytes: bytes = await file.read()
    if len(audio_bytes) == 0:
        raise HTTPException(status_code=400, detail="Fichier audio vide.")

    try:
        raw_text: str = await transcribe_audio(
            audio_bytes, file.filename or "recording.webm"
        )
    except httpx.HTTPStatusError as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Erreur transcription Voxtral : {exc}",
        )
    except httpx.RequestError as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Erreur connexion Voxtral : {exc}",
        )

    return TranscriptionResponse(raw_transcription=raw_text)


# ---------------------------------------------------------------------------
# Mise en forme
# ---------------------------------------------------------------------------


@app.post("/format", response_model=FormatResponse)
async def format_text(req: FormatRequest) -> FormatResponse:
    """Etape 2 : Mise en forme du transcript en compte-rendu structure.

    Detecte l'organe, applique le template correspondant, formate le
    rapport et detecte les donnees manquantes.
    """
    if not req.raw_text.strip():
        raise HTTPException(status_code=400, detail="Texte vide.")

    try:
        formatted: str
        organe: str
        formatted, organe = await format_transcription(
            req.raw_text, req.rapport_precedent
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=422, detail=f"Erreur de validation : {exc}"
        )
    except httpx.HTTPStatusError as exc:
        raise HTTPException(
            status_code=502, detail=f"Erreur formatting Mistral : {exc}"
        )
    except httpx.RequestError as exc:
        raise HTTPException(
            status_code=502, detail=f"Erreur connexion Mistral : {exc}"
        )

    # Detection des donnees manquantes
    donnees_manquantes: list[DonneeManquante] = detecter_donnees_manquantes(
        formatted, organe
    )

    return FormatResponse(
        formatted_report=formatted,
        organe_detecte=organe,
        donnees_manquantes=donnees_manquantes,
    )


# ---------------------------------------------------------------------------
# Iteration (ajout a un rapport existant)
# ---------------------------------------------------------------------------


@app.post("/iterate", response_model=IterationResponse)
async def iterate_report(req: IterationRequest) -> IterationResponse:
    """Etape 2bis : Ajout d'une dictee complementaire a un rapport existant.

    Integre le nouveau transcript dans le rapport actuel, met a jour les
    marqueurs de donnees manquantes.
    """
    if not req.rapport_actuel.strip():
        raise HTTPException(status_code=400, detail="Rapport actuel vide.")
    if not req.nouveau_transcript.strip():
        raise HTTPException(status_code=400, detail="Nouveau transcript vide.")

    try:
        updated: str
        organe: str
        updated, organe = await iterer_rapport(
            req.rapport_actuel, req.nouveau_transcript
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=422, detail=f"Erreur de validation : {exc}"
        )
    except httpx.HTTPStatusError as exc:
        raise HTTPException(
            status_code=502, detail=f"Erreur iteration Mistral : {exc}"
        )
    except httpx.RequestError as exc:
        raise HTTPException(
            status_code=502, detail=f"Erreur connexion Mistral : {exc}"
        )

    # Re-detection des donnees manquantes apres iteration
    donnees_manquantes: list[DonneeManquante] = detecter_donnees_manquantes(
        updated, organe
    )

    return IterationResponse(
        formatted_report=updated,
        organe_detecte=organe,
        donnees_manquantes=donnees_manquantes,
    )


# ---------------------------------------------------------------------------
# Decoupage en sections
# ---------------------------------------------------------------------------


class _SectionsRequest(BaseModel):
    """Requete interne pour le decoupage en sections."""

    formatted_report: str


@app.post("/sections", response_model=SectionsResponse)
async def get_sections(req: _SectionsRequest) -> SectionsResponse:
    """Decoupe un rapport formate en sections nommees pour copie individuelle.

    Sections reconnues : titre, renseignements_cliniques, macroscopie,
    microscopie, ihc, biologie_moleculaire, conclusion.
    """
    if not req.formatted_report.strip():
        raise HTTPException(status_code=400, detail="Rapport vide.")

    sections: dict[str, str] = split_report_sections(req.formatted_report)

    return SectionsResponse(sections=sections)


# ---------------------------------------------------------------------------
# Export Word
# ---------------------------------------------------------------------------


@app.post("/export")
async def export_docx(req: ExportRequest) -> StreamingResponse:
    """Etape 3 : Export du compte-rendu en document Word .docx.

    Les marqueurs [A COMPLETER: xxx] sont rendus en rouge et gras.
    """
    try:
        doc_bytes: bytes = markdown_to_docx(req.formatted_report, req.title)
    except ValueError as exc:
        raise HTTPException(
            status_code=500, detail=f"Erreur export Word : {exc}"
        )

    buffer: io.BytesIO = io.BytesIO(doc_bytes)
    return StreamingResponse(
        buffer,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={
            "Content-Disposition": "attachment; filename=compte-rendu.docx"
        },
    )


# ---------------------------------------------------------------------------
# Serving du frontend (production)
# ---------------------------------------------------------------------------

_FRONTEND_DIST: Path = Path(__file__).resolve().parent.parent / "frontend" / "dist"

if _FRONTEND_DIST.is_dir():
    from starlette.responses import FileResponse

    # Monter les assets statiques (JS, CSS, images)
    app.mount(
        "/assets",
        StaticFiles(directory=str(_FRONTEND_DIST / "assets")),
        name="static-assets",
    )

    @app.get("/{full_path:path}")
    async def serve_frontend(full_path: str) -> FileResponse:
        """Sert le frontend React pour toutes les routes non-API."""
        file_path: Path = _FRONTEND_DIST / full_path
        if file_path.is_file():
            return FileResponse(str(file_path))
        return FileResponse(str(_FRONTEND_DIST / "index.html"))
