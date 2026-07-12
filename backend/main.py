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
import logging
from contextlib import asynccontextmanager
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Annotated

import httpx
from fastapi import Depends, FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
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
from export_docx import markdown_to_docx, split_report_sections
from detection_manquantes import (
    detecter_donnees_manquantes,
    detecter_champs_obligatoires_manquants,
    calculer_score_completude,
)
from adicap import suggerer_adicap
from snomed import suggerer_snomed
from config import get_settings, validate_settings_at_startup
from database import close_engine, create_tables
from auth import get_current_user
from db_models import User
from llm.base import LLMError, LLMTimeoutError, LLMTransientError
from reports import GeneratedReport, ReportEngine, get_report_engine, reset_report_engine
from reports.guardrails import GenerationParseError, filter_present_alertes
from routes_auth import router as auth_router
from routes_reports import router as reports_router
from routes_admin import router as admin_router

logger = logging.getLogger("anapath.api")

from rate_limit import limiter  # limiteur partage (evite l'import circulaire)


# ---------------------------------------------------------------------------
# Application lifecycle
# ---------------------------------------------------------------------------


def _configure_logging() -> None:
    """Logging structure au demarrage (sinon les logger.info restent muets)."""
    import logging
    import os

    level = os.environ.get("LOG_LEVEL", "INFO").upper()
    logging.basicConfig(
        level=getattr(logging, level, logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        force=True,
    )


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """Gestion du cycle de vie de l'application."""
    _configure_logging()
    validate_settings_at_startup()
    await create_tables()
    yield
    engine = reset_report_engine()
    if engine is not None:
        await engine.aclose()
    # Fermeture du client STT (evite une fuite de ressource au shutdown).
    from transcription import close_httpx_client

    await close_httpx_client()
    await close_engine()


app: FastAPI = FastAPI(
    title="Anapath - Dictee medicale",
    version="0.7.0",
    lifespan=lifespan,
)

app.state.limiter = limiter


@app.exception_handler(RateLimitExceeded)
async def _rate_limit_handler(
    _request: Request, exc: RateLimitExceeded
) -> JSONResponse:
    """Renvoie 429 (et non 500) en cas de depassement de quota."""
    return JSONResponse(
        status_code=429,
        content={"detail": f"Trop de requetes. Reessayez ({exc.detail})."},
    )

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
    engine: Annotated[ReportEngine, Depends(get_report_engine)],
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
        transcript = await engine.transcribe(audio_bytes, filename)
    except LLMTransientError as exc:
        # Voxtral indisponible apres retries -> 503 (reessayer plus tard)
        raise HTTPException(
            status_code=503,
            detail=f"Service de transcription momentanement indisponible : {exc}",
        )
    except httpx.HTTPStatusError as exc:
        raise HTTPException(
            status_code=502, detail=f"Erreur transcription : {exc}"
        )
    except httpx.RequestError as exc:
        raise HTTPException(
            status_code=502, detail=f"Erreur connexion transcription : {exc}"
        )

    return TranscriptionResponse(raw_transcription=transcript.text)


def _map_generation_error(exc: Exception) -> HTTPException:
    """Traduit une erreur du moteur en HTTPException adaptee."""
    if isinstance(exc, GenerationParseError):
        return HTTPException(
            status_code=502,
            detail=f"Reponse du moteur inexploitable : {exc}",
        )
    if isinstance(exc, LLMTimeoutError):
        return HTTPException(
            status_code=504, detail="Le moteur de generation n'a pas repondu a temps."
        )
    if isinstance(exc, LLMError):
        return HTTPException(status_code=502, detail=f"Erreur moteur : {exc}")
    if isinstance(exc, ValueError):
        return HTTPException(status_code=422, detail=f"Erreur de validation : {exc}")
    logger.exception("Erreur inattendue du moteur de generation")
    return HTTPException(status_code=500, detail="Erreur interne de generation.")


# ---------------------------------------------------------------------------
# Mise en forme
# ---------------------------------------------------------------------------


@app.post("/format", response_model=FormatResponse)
@limiter.limit("20/minute")
async def format_text(
    request: Request,
    _user: Annotated[User, Depends(get_current_user)],
    engine: Annotated[ReportEngine, Depends(get_report_engine)],
    req: FormatRequest,
) -> FormatResponse:
    """Etape 2 : Mise en forme du transcript en compte-rendu structure."""
    if not req.raw_text.strip():
        raise HTTPException(status_code=400, detail="Texte vide.")

    try:
        result: GeneratedReport = await engine.generate(
            req.raw_text,
            rapport_precedent=req.rapport_precedent,
        )
    except Exception as exc:  # noqa: BLE001 - traduit en HTTPException typee
        raise _map_generation_error(exc)

    return _to_format_response(result)


def _merge_donnees_manquantes(
    deterministes: list[DonneeManquante], recommandees: list[DonneeManquante]
) -> list[DonneeManquante]:
    """Fusionne les champs manquants deterministes (marqueurs [A COMPLETER],
    obligatoires) et les recommandations LLM (probabilistes), en dedupliquant :
    un champ deja couvert par un marqueur deterministe n'est pas re-liste."""

    def _norm(s: str) -> str:
        import unicodedata

        s = unicodedata.normalize("NFD", s).encode("ascii", "ignore").decode()
        return "".join(c for c in s.lower() if c.isalnum())

    resultat: list[DonneeManquante] = list(deterministes)
    vus: list[str] = [_norm(d.champ) for d in deterministes]
    for reco in recommandees:
        cle = _norm(reco.champ)
        if not cle:
            continue
        # Dédoublonnage par inclusion : "ptnm" et "ptnmtnm8esein" sont le même champ.
        if any(cle in v or v in cle for v in vus):
            continue
        resultat.append(reco)
        vus.append(cle)
    return resultat


def _safety_filter_panel(
    donnees: list[DonneeManquante], result: GeneratedReport
) -> list[DonneeManquante]:
    """Filtre de securite du panneau FINAL (marqueurs deterministes inclus).

    Garantit qu'aucun champ hors-contexte organe / prelevement / nature de lesion
    ne peut apparaitre, quelle que soit sa source (LLM ou marqueur [A COMPLETER]) :
    un champ tumoral ne peut pas apparaitre sur une lesion benigne.
    """
    from reports.guardrails import filter_alertes
    from specimen_type import SpecimenType, detecter_diagnostic_context

    try:
        specimen = SpecimenType(result.type_prelevement)
    except ValueError:
        specimen = SpecimenType.INDETERMINE
    contexte = detecter_diagnostic_context(result.cr).value
    filtres, _ = filter_alertes(donnees, result.organes_detectes, specimen, contexte)
    return filtres


def _build_panel(result: GeneratedReport) -> list[DonneeManquante]:
    """Construit le panneau "a completer" — pipeline complet, partage format/iterate.

    Sources fusionnees : (1) marqueurs [A COMPLETER] du CR (deterministes), (2)
    RAPPEL DETERMINISTE des champs obligatoires INCa applicables absents (comble
    les oublis du LLM sur les pieces), (3) recommandations du LLM. Puis double
    garde : filtre de securite (hors-contexte) + anti-faux-positif (deja present).
    """
    marqueurs: list[DonneeManquante] = detecter_donnees_manquantes(
        result.cr, result.organe
    )
    obligatoires: list[DonneeManquante] = detecter_champs_obligatoires_manquants(
        result.cr, result.organes_detectes
    )
    panel = _merge_donnees_manquantes(marqueurs + obligatoires, result.alertes)
    panel = _safety_filter_panel(panel, result)
    panel, _ = filter_present_alertes(panel, result.cr)
    panel = _polish_panel(panel, result.cr)
    return panel


def _polish_panel(
    panel: list[DonneeManquante], cr: str
) -> list[DonneeManquante]:
    """Finition du panneau : retire les champs inadaptes au sous-site — le
    'mesorectum' (concept RECTAL) n'a pas de sens sur un colon/sigmoide."""
    import unicodedata

    def _norm(s: str) -> str:
        s = unicodedata.normalize("NFD", s).encode("ascii", "ignore").decode()
        return s.lower()

    low_cr = _norm(cr)
    has_rectum = "rectum" in low_cr or "rectal" in low_cr
    # Le grade FNCLCC ne s'applique PAS aux sarcomes a cellules rondes / pediatriques
    # (rhabdomyosarcome, Ewing, neuroblastome... : haut grade par definition, autres
    # systemes IRS/COG/SIOP). On retire le champ FNCLCC dans ce contexte.
    sarcome_non_fnclcc = any(
        w in low_cr for w in ("rhabdomyosarcome", "ewing", "neuroblastome",
                              "embryonnaire", "desmoplastique a petites cellules",
                              "pnet")
    )

    def _garder(d: DonneeManquante) -> bool:
        n = _norm(d.champ)
        if "mesorect" in n and not has_rectum:
            return False
        if "fnclcc" in n and sarcome_non_fnclcc:
            return False
        return True

    return [d for d in panel if _garder(d)]


def _to_format_response(result: GeneratedReport) -> FormatResponse:
    """Assemble la reponse API : marqueurs deterministes + recommandations filtrees."""
    return FormatResponse(
        formatted_report=result.cr,
        organe_detecte=result.organe,
        donnees_manquantes=_build_panel(result),
        warnings=result.warnings,
        organes_detectes=result.organes_detectes,
        type_prelevement=result.type_prelevement,
        coherence=result.coherence,
    )


# ---------------------------------------------------------------------------
# Iteration (ajout a un rapport existant)
# ---------------------------------------------------------------------------


@app.post("/iterate", response_model=IterationResponse)
@limiter.limit("20/minute")
async def iterate_report(
    request: Request,
    _user: Annotated[User, Depends(get_current_user)],
    engine: Annotated[ReportEngine, Depends(get_report_engine)],
    req: IterationRequest,
) -> IterationResponse:
    """Etape 2bis : Ajout d'une dictee complementaire a un rapport existant."""
    if not req.rapport_actuel.strip():
        raise HTTPException(status_code=400, detail="Rapport actuel vide.")
    if not req.nouveau_transcript.strip():
        raise HTTPException(status_code=400, detail="Nouveau transcript vide.")

    try:
        result: GeneratedReport = await engine.iterate(
            req.rapport_actuel, req.nouveau_transcript
        )
    except Exception as exc:  # noqa: BLE001 - traduit en HTTPException typee
        raise _map_generation_error(exc)

    return IterationResponse(
        formatted_report=result.cr,
        organe_detecte=result.organe,
        donnees_manquantes=_build_panel(result),
        warnings=result.warnings,
        organes_detectes=result.organes_detectes,
        type_prelevement=result.type_prelevement,
        coherence=result.coherence,
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
