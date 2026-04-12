"""API FastAPI Anapath v4.

Endpoints principaux :
- POST /transcribe : transcription audio via Voxtral
- POST /format     : dictee -> CRDocument structure + markdown rendu (agent v4)
- POST /iterate    : ajout d'une dictee complementaire a un rapport
- POST /export     : export Word .docx
- GET  /health     : verification du statut

Le pipeline metier vit dans ``agent.py``. Ce fichier ne contient que la
plomberie HTTP, validation de fichier audio, gestion d'erreurs et
montage du frontend en production.
"""

import io
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated

import anthropic
import httpx
from fastapi import Depends, FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from slowapi import Limiter
from slowapi.util import get_remote_address
from starlette.requests import Request

from agent import produce_cr
from auth import get_current_user
from config import get_settings, validate_settings_at_startup
from database import close_engine, create_tables
from db_models import User
from models import (
    ExportRequest,
    FormatRequest,
    FormatResponse,
    IterationRequest,
    IterationResponse,
    TranscriptionResponse,
)
from pydantic import BaseModel
from routes_admin import router as admin_router
from routes_auth import router as auth_router
from routes_reports import router as reports_router
from transcription import transcribe_audio
from export_docx import markdown_to_docx, split_report_sections


limiter = Limiter(key_func=get_remote_address)


# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """Gestion du cycle de vie de l'application."""
    validate_settings_at_startup()
    await create_tables()
    yield
    await close_engine()


app: FastAPI = FastAPI(
    title="Anapath - Dictee medicale",
    version="4.0.0",
    lifespan=lifespan,
)

app.state.limiter = limiter

_settings = get_settings()
_cors_origins: list[str] = [
    o.strip() for o in _settings.cors_origins.split(",") if o.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routers
app.include_router(auth_router)
app.include_router(reports_router)
app.include_router(admin_router)


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------


@app.get("/health")
async def health() -> dict[str, str]:
    """Verification du statut de l'API."""
    return {"status": "ok", "version": "4.0.0"}


# ---------------------------------------------------------------------------
# Transcription audio (inchange par rapport a v3)
# ---------------------------------------------------------------------------


ALLOWED_AUDIO_PREFIXES: list[str] = ["audio/", "video/"]
ALLOWED_EXTENSIONS: set[str] = {
    ".webm", ".mp3", ".mp4", ".m4a", ".mov", ".wav", ".ogg", ".flac", ".aac",
}


def _validate_audio_file(content_type: str, filename: str) -> None:
    """Valide le format du fichier audio."""
    ext: str = ""
    if "." in filename:
        ext = "." + filename.rsplit(".", 1)[-1].lower()

    type_ok: bool = any(content_type.startswith(p) for p in ALLOWED_AUDIO_PREFIXES)
    ext_ok: bool = ext in ALLOWED_EXTENSIONS

    if not type_ok and not ext_ok:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Format non supporte ({content_type}, {ext}). "
                f"Formats acceptes : {', '.join(sorted(ALLOWED_EXTENSIONS))}"
            ),
        )


_MAX_UPLOAD_BYTES: int = _settings.max_upload_size_mb * 1024 * 1024


@app.post("/transcribe", response_model=TranscriptionResponse)
@limiter.limit("30/minute")
async def transcribe(
    request: Request,  # noqa: ARG001  # requis par slowapi
    _user: Annotated[User, Depends(get_current_user)],
    file: UploadFile = File(...),
) -> TranscriptionResponse:
    """Etape 1 : transcription audio via Voxtral."""
    content_type: str = file.content_type or ""
    filename: str = file.filename or "recording.webm"

    _validate_audio_file(content_type, filename)

    audio_bytes: bytes = await file.read()
    if len(audio_bytes) == 0:
        raise HTTPException(status_code=400, detail="Fichier audio vide.")

    if len(audio_bytes) > _MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"Fichier trop volumineux (max {_settings.max_upload_size_mb} Mo).",
        )

    try:
        raw_text: str = await transcribe_audio(audio_bytes, filename)
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
# Formatage v4 — appelle l'agent
# ---------------------------------------------------------------------------


@app.post("/format", response_model=FormatResponse)
@limiter.limit("20/minute")
async def format_text(
    request: Request,  # noqa: ARG001
    _user: Annotated[User, Depends(get_current_user)],
    req: FormatRequest,
) -> FormatResponse:
    """Etape 2 : dictee -> CR structure via le pipeline v4."""
    if not req.raw_text.strip():
        raise HTTPException(status_code=400, detail="Texte vide.")

    try:
        result = await produce_cr(req.raw_text)
    except anthropic.APIStatusError as exc:
        raise HTTPException(
            status_code=502, detail=f"Erreur Claude : {exc}"
        )
    except anthropic.APIConnectionError as exc:
        raise HTTPException(
            status_code=502, detail=f"Erreur connexion Claude : {exc}"
        )

    return FormatResponse(
        trace_id=result.trace_id,
        formatted_report=result.formatted_report,
        document=result.document,
        classification=result.classification,
        markers=result.markers,
    )


# ---------------------------------------------------------------------------
# Iteration v4
# ---------------------------------------------------------------------------


@app.post("/iterate", response_model=IterationResponse)
@limiter.limit("20/minute")
async def iterate_report(
    request: Request,  # noqa: ARG001
    _user: Annotated[User, Depends(get_current_user)],
    req: IterationRequest,
) -> IterationResponse:
    """Etape 2bis : integrer une nouvelle dictee dans un rapport existant.

    Strategie simple : on concatene le rapport actuel (contexte) et le
    nouveau transcript, on passe le tout au pipeline. L'agent relit ses
    exemples et regle a jour la structure. Pas de branche d'iteration
    specifique : la determination d'un rapport existant se fait par la
    presence du texte prefixe dans la dictee.
    """
    if not req.rapport_actuel.strip():
        raise HTTPException(status_code=400, detail="Rapport actuel vide.")
    if not req.nouveau_transcript.strip():
        raise HTTPException(status_code=400, detail="Nouveau transcript vide.")

    combined: str = (
        f"{req.rapport_actuel}\n\n[NOUVELLE DICTEE]\n{req.nouveau_transcript}"
    )

    try:
        result = await produce_cr(combined)
    except anthropic.APIStatusError as exc:
        raise HTTPException(
            status_code=502, detail=f"Erreur Claude : {exc}"
        )
    except anthropic.APIConnectionError as exc:
        raise HTTPException(
            status_code=502, detail=f"Erreur connexion Claude : {exc}"
        )

    return IterationResponse(
        trace_id=result.trace_id,
        formatted_report=result.formatted_report,
        document=result.document,
        classification=result.classification,
        markers=result.markers,
    )


# ---------------------------------------------------------------------------
# Sections (helper pour l'edition par section dans le frontend)
# ---------------------------------------------------------------------------


class _SectionsRequest(BaseModel):
    """Requete pour decouper un rapport en sections editables."""

    formatted_report: str


class _SectionsResponse(BaseModel):
    """Reponse avec les sections nommees extraites du markdown."""

    sections: dict[str, str]


@app.post("/sections", response_model=_SectionsResponse)
async def get_sections(
    _user: Annotated[User, Depends(get_current_user)],
    req: _SectionsRequest,
) -> _SectionsResponse:
    """Decoupe un rapport markdown en sections nommees pour l'editeur frontend."""
    if not req.formatted_report.strip():
        raise HTTPException(status_code=400, detail="Rapport vide.")
    sections: dict[str, str] = split_report_sections(req.formatted_report)
    return _SectionsResponse(sections=sections)


# ---------------------------------------------------------------------------
# Export Word
# ---------------------------------------------------------------------------


@app.post("/export")
async def export_docx(
    _user: Annotated[User, Depends(get_current_user)],
    req: ExportRequest,
) -> StreamingResponse:
    """Export du compte-rendu en document Word .docx."""
    try:
        doc_bytes: bytes = markdown_to_docx(req.formatted_report, req.title)
    except ValueError as exc:
        raise HTTPException(
            status_code=500, detail=f"Erreur export Word : {exc}"
        )

    buffer: io.BytesIO = io.BytesIO(doc_bytes)
    return StreamingResponse(
        buffer,
        media_type=(
            "application/vnd.openxmlformats-officedocument."
            "wordprocessingml.document"
        ),
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

    app.mount(
        "/assets",
        StaticFiles(directory=str(_FRONTEND_DIST / "assets")),
        name="static-assets",
    )

    @app.get("/{full_path:path}")
    async def serve_frontend(full_path: str) -> FileResponse:
        """Sert le frontend React pour toutes les routes non-API."""
        file_path: Path = (_FRONTEND_DIST / full_path).resolve()
        if not str(file_path).startswith(str(_FRONTEND_DIST.resolve())):
            return FileResponse(str(_FRONTEND_DIST / "index.html"))
        if file_path.is_file():
            return FileResponse(str(file_path))
        return FileResponse(str(_FRONTEND_DIST / "index.html"))
