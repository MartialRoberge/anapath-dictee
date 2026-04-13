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
from contextlib import asynccontextmanager
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Annotated

import anthropic
import httpx
from fastapi import Depends, FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from slowapi import Limiter
from slowapi.util import get_remote_address
from starlette.requests import Request

from models import (
    TranscriptionResponse,
    FormatRequest,
    FormatResponse,
    IterationRequest,
    IterationResponse,
    ExportRequest,
    SectionsResponse,
    DonneeManquante,
    AdicapRequest,
    AdicapResponse,
    SnomedCode,
    SnomedResponse,
    CompletudeRequest,
    CompletudeResponse,
)
from transcription import transcribe_audio
from formatting import format_transcription, iterer_rapport
from export_docx import markdown_to_docx, split_report_sections
from detection_manquantes import detecter_donnees_manquantes, calculer_score_completude
from adicap import suggerer_adicap
from snomed import suggerer_snomed
from config import get_settings, validate_settings_at_startup
from database import close_engine, create_tables
from auth import get_current_user
from db_models import User
from routes_auth import router as auth_router
from routes_reports import router as reports_router
from routes_admin import router as admin_router

limiter = Limiter(key_func=get_remote_address)


# ---------------------------------------------------------------------------
# Application lifecycle
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
    version="0.6.0",
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
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# Transcription audio
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
            detail=f"Format non supporte ({content_type}, {ext}). "
            f"Formats acceptes : {', '.join(sorted(ALLOWED_EXTENSIONS))}",
        )


_MAX_UPLOAD_BYTES: int = _settings.max_upload_size_mb * 1024 * 1024


@app.post("/transcribe", response_model=TranscriptionResponse)
@limiter.limit("30/minute")
async def transcribe(
    request: Request,
    _user: Annotated[User, Depends(get_current_user)],
    file: UploadFile = File(...),
) -> TranscriptionResponse:
    """Etape 1 : Transcription audio via Voxtral."""
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
# Mise en forme
# ---------------------------------------------------------------------------


@app.post("/format", response_model=FormatResponse)
@limiter.limit("20/minute")
async def format_text(
    request: Request,
    _user: Annotated[User, Depends(get_current_user)],
    req: FormatRequest,
) -> FormatResponse:
    """Etape 2 : Mise en forme du transcript en compte-rendu structure."""
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
    except anthropic.APIStatusError as exc:
        raise HTTPException(
            status_code=502, detail=f"Erreur formatting Claude : {exc}"
        )
    except anthropic.APIConnectionError as exc:
        raise HTTPException(
            status_code=502, detail=f"Erreur connexion Claude : {exc}"
        )

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
@limiter.limit("20/minute")
async def iterate_report(
    request: Request,
    _user: Annotated[User, Depends(get_current_user)],
    req: IterationRequest,
) -> IterationResponse:
    """Etape 2bis : Ajout d'une dictee complementaire a un rapport existant."""
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
    except anthropic.APIStatusError as exc:
        raise HTTPException(
            status_code=502, detail=f"Erreur iteration Claude : {exc}"
        )
    except anthropic.APIConnectionError as exc:
        raise HTTPException(
            status_code=502, detail=f"Erreur connexion Claude : {exc}"
        )

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
async def get_sections(
    _user: Annotated[User, Depends(get_current_user)],
    req: _SectionsRequest,
) -> SectionsResponse:
    """Decoupe un rapport formate en sections nommees."""
    if not req.formatted_report.strip():
        raise HTTPException(status_code=400, detail="Rapport vide.")

    sections: dict[str, str] = split_report_sections(req.formatted_report)

    return SectionsResponse(sections=sections)


# ---------------------------------------------------------------------------
# ADICAP
# ---------------------------------------------------------------------------


@app.post("/adicap", response_model=AdicapResponse)
async def get_adicap(
    _user: Annotated[User, Depends(get_current_user)],
    req: AdicapRequest,
) -> AdicapResponse:
    """Suggere un code ADICAP depuis le rapport structure."""
    if not req.formatted_report.strip():
        raise HTTPException(status_code=400, detail="Rapport vide.")

    result: dict[str, str] = suggerer_adicap(
        req.formatted_report, req.organe_detecte
    )
    return AdicapResponse(**result)


# ---------------------------------------------------------------------------
# SNOMED CT
# ---------------------------------------------------------------------------


@app.post("/snomed", response_model=SnomedResponse)
async def get_snomed(
    _user: Annotated[User, Depends(get_current_user)],
    req: AdicapRequest,
) -> SnomedResponse:
    """Suggere des codes SNOMED CT depuis le rapport structure."""
    if not req.formatted_report.strip():
        raise HTTPException(status_code=400, detail="Rapport vide.")

    result = suggerer_snomed(req.formatted_report, req.organe_detecte)
    topo = result["topography"]
    morpho = result["morphology"]

    return SnomedResponse(
        topography=SnomedCode(**topo),  # type: ignore[arg-type]
        morphology=SnomedCode(**morpho),  # type: ignore[arg-type]
    )


# ---------------------------------------------------------------------------
# Completude INCa
# ---------------------------------------------------------------------------


@app.post("/completude", response_model=CompletudeResponse)
async def get_completude(
    _user: Annotated[User, Depends(get_current_user)],
    req: CompletudeRequest,
) -> CompletudeResponse:
    """Calcule le score de completude INCa du rapport."""
    if not req.formatted_report.strip():
        raise HTTPException(status_code=400, detail="Rapport vide.")

    result: dict[str, int | float] = calculer_score_completude(
        req.formatted_report, req.organe_detecte
    )
    return CompletudeResponse(
        score=int(result["score"]),
        total_champs=int(result["total_champs"]),
        champs_presents=int(result["champs_presents"]),
        pourcentage=float(result["pourcentage"]),
    )


# ---------------------------------------------------------------------------
# Export Word
# ---------------------------------------------------------------------------


@app.post("/export")
async def export_docx(
    _user: Annotated[User, Depends(get_current_user)],
    req: ExportRequest,
) -> StreamingResponse:
    """Etape 3 : Export du compte-rendu en document Word .docx."""
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

    app.mount(
        "/assets",
        StaticFiles(directory=str(_FRONTEND_DIST / "assets")),
        name="static-assets",
    )

    @app.get("/{full_path:path}")
    async def serve_frontend(full_path: str) -> FileResponse:
        """Sert le frontend React pour toutes les routes non-API."""
        file_path: Path = (_FRONTEND_DIST / full_path).resolve()
        # Protection contre le path traversal
        if not str(file_path).startswith(str(_FRONTEND_DIST.resolve())):
            return FileResponse(str(_FRONTEND_DIST / "index.html"))
        if file_path.is_file():
            return FileResponse(str(file_path))
        return FileResponse(str(_FRONTEND_DIST / "index.html"))
