"""Routes MARC v3 (/v3/projets...). AUCUNE persistance de la dictee, de l'audio ni du CR.

- POST /v3/projets            {dictee}         -> SSE (step, partial, projet, error) ou JSON si ?stream=false
- POST /v3/projets/audio      multipart audio  -> idem, avec etape de transcription
- POST /v3/projets/iterer     IterationRequest -> idem, ids d'elements conserves
- POST /v3/projets/export/docx Projet          -> .docx (trous rendus « [A COMPLETER : libelle] »)
- GET  /v3/kb/sources/{id}                     -> fiche lisible de la source (titre_court, description, fiabilite_sens, references)
"""


import asyncio
import io
import json
import logging
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile
from fastapi.responses import JSONResponse, StreamingResponse

from auth import get_current_user
from config import get_settings
from db_models import User
from projet.export_docx import projet_vers_docx
from projet.llm_client import ClientLLM, get_client_llm
from projet.orchestrateur import Pipeline, PipelineErreur, Transcripteur, projet_de_secours
from projet.referentiel import Referentiel
from projet.schemas import IterationRequest, Projet, ProjetRequest
from rate_limit import limiter

logger = logging.getLogger("marc.v3.routes")

router = APIRouter(prefix="/v3", tags=["v3"])

_EXTENSIONS_AUDIO = {".webm", ".mp3", ".mp4", ".m4a", ".mov", ".wav", ".ogg", ".flac", ".aac"}


def get_referentiel() -> Referentiel:
    """Dependance : referentiel neuf par requete (les replis sont propres a chaque passage)."""
    return Referentiel()


def get_transcripteur() -> Transcripteur:
    """Dependance : transcription Voxtral existante (remplacee dans les tests)."""
    from transcription import transcribe_audio
    return transcribe_audio


Lanceur = Callable[[Pipeline], Awaitable[Projet]]


def _sse(evenement: str, donnees: object) -> str:
    return f"event: {evenement}\ndata: {json.dumps(donnees, ensure_ascii=False)}\n\n"


async def _flux(pipeline_factory: Callable[[Callable[[str, dict], Awaitable[None]]], Pipeline],
                lancer: Lanceur, dictee_secours: str, request: Request) -> AsyncIterator[str]:
    """Execute le pipeline en tache de fond et relaie ses evenements en SSE."""
    file: asyncio.Queue[tuple[str, object] | None] = asyncio.Queue()

    async def emettre(evt: str, data: dict) -> None:
        await file.put((evt, data))

    pipeline = pipeline_factory(emettre)

    async def tache() -> None:
        try:
            projet = await lancer(pipeline)
            await file.put(("projet", projet.model_dump()))
        except PipelineErreur as exc:
            await file.put(("error", {"message": str(exc), "recuperable": exc.recuperable}))
        except Exception as exc:  # noqa: BLE001 - dernier filet : projet minimal fidele
            logger.exception("pipeline v3 en échec")
            if dictee_secours.strip():
                secours = projet_de_secours(dictee_secours, f"erreur interne ({type(exc).__name__})")
                secours.trace = list(pipeline.traceur.etapes)
                await file.put(("projet", secours.model_dump()))
            else:
                await file.put(("error", {"message": "Erreur interne de génération.", "recuperable": True}))
        finally:
            await file.put(None)

    t = asyncio.create_task(tache())
    try:
        while True:
            item = await file.get()
            if item is None:
                break
            yield _sse(item[0], item[1])
            if await request.is_disconnected():
                t.cancel()
                break
    finally:
        if not t.done():
            t.cancel()


async def _repondre(request: Request, stream: bool, fabrique: Callable[..., Pipeline], lancer: Lanceur,
                    dictee_secours: str):
    if stream:
        return StreamingResponse(
            _flux(lambda em: fabrique(em), lancer, dictee_secours, request),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )
    pipeline = fabrique(None)
    try:
        projet = await lancer(pipeline)
    except PipelineErreur as exc:
        raise HTTPException(status_code=422 if exc.recuperable else 503, detail=str(exc))
    except Exception as exc:  # noqa: BLE001
        logger.exception("pipeline v3 en échec")
        if not dictee_secours.strip():
            raise HTTPException(status_code=500, detail="Erreur interne de génération.")
        projet = projet_de_secours(dictee_secours, f"erreur interne ({type(exc).__name__})")
        projet.trace = list(pipeline.traceur.etapes)
    return JSONResponse(projet.model_dump())


@router.post("/projets")
@limiter.limit("30/minute")
async def creer_projet(
    request: Request,
    req: ProjetRequest,
    _user: Annotated[User, Depends(get_current_user)],
    client: Annotated[ClientLLM, Depends(get_client_llm)],
    referentiel: Annotated[Referentiel, Depends(get_referentiel)],
    stream: bool = Query(default=True),
):
    """Dictee texte -> projet de CR (flux SSE par defaut)."""
    if not req.dictee.strip():
        raise HTTPException(status_code=400, detail="Dictée vide.")

    def fabrique(em):
        return Pipeline(client, referentiel=referentiel, emettre=em)

    return await _repondre(request, stream, fabrique, lambda p: p.executer(dictee=req.dictee), req.dictee)


@router.post("/projets/audio")
@limiter.limit("30/minute")
async def creer_projet_audio(
    request: Request,
    _user: Annotated[User, Depends(get_current_user)],
    client: Annotated[ClientLLM, Depends(get_client_llm)],
    referentiel: Annotated[Referentiel, Depends(get_referentiel)],
    transcrire: Annotated[Transcripteur, Depends(get_transcripteur)],
    audio: UploadFile = File(...),
    stream: bool = Query(default=True),
):
    """Audio -> transcription (Voxtral) -> projet. L'audio reste en memoire, jamais ecrit."""
    nom = audio.filename or "dictee.webm"
    ext = "." + nom.rsplit(".", 1)[-1].lower() if "." in nom else ""
    type_ok = (audio.content_type or "").startswith(("audio/", "video/"))
    if not type_ok and ext not in _EXTENSIONS_AUDIO:
        raise HTTPException(status_code=400, detail="Format audio non supporté.")
    octets = await audio.read()
    if not octets:
        raise HTTPException(status_code=400, detail="Fichier audio vide.")
    if len(octets) > get_settings().max_upload_size_mb * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Fichier audio trop volumineux.")

    def fabrique(em):
        return Pipeline(client, referentiel=referentiel, emettre=em, transcrire=transcrire)

    return await _repondre(request, stream, fabrique, lambda p: p.executer(audio=(octets, nom)), "")


@router.post("/projets/iterer")
@limiter.limit("30/minute")
async def iterer_projet(
    request: Request,
    req: IterationRequest,
    _user: Annotated[User, Depends(get_current_user)],
    client: Annotated[ClientLLM, Depends(get_client_llm)],
    referentiel: Annotated[Referentiel, Depends(get_referentiel)],
    stream: bool = Query(default=True),
):
    """Ajoute une dictee complementaire (ex. resultat IHC) au projet, ids conserves."""
    if not req.dictee_complementaire.strip():
        raise HTTPException(status_code=400, detail="Dictée complémentaire vide.")

    def fabrique(em):
        return Pipeline(client, referentiel=referentiel, emettre=em)

    secours = req.projet.dictee.corrigee + "\n\n" + req.dictee_complementaire
    return await _repondre(request, stream, fabrique,
                           lambda p: p.iterer(req.projet, req.dictee_complementaire), secours)


@router.post("/projets/export/docx")
async def exporter_docx(
    projet: Projet,
    _user: Annotated[User, Depends(get_current_user)],
) -> StreamingResponse:
    """Projet -> document Word (en memoire)."""
    try:
        octets = projet_vers_docx(projet)
    except Exception as exc:  # noqa: BLE001
        logger.exception("export docx v3")
        raise HTTPException(status_code=500, detail=f"Export Word impossible : {type(exc).__name__}")
    return StreamingResponse(
        io.BytesIO(octets),
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": "attachment; filename=projet-compte-rendu.docx"},
    )


@router.get("/kb/sources/{source_id:path}")
async def lire_source(
    source_id: str,
    _user: Annotated[User, Depends(get_current_user)],
    referentiel: Annotated[Referentiel, Depends(get_referentiel)],
    limite: int = 50,
) -> dict:
    """Fiche lisible d'une source : titre, description, editeur, version, fiabilite expliquee, licence,
    url et entrees de la base (champs, regles...) qui la citent (``references``, ``limite`` <= 500)."""
    detail = referentiel.source_detail(source_id, limite=max(0, min(limite, 500)))
    if not detail:
        raise HTTPException(status_code=404, detail="Source inconnue.")
    return detail
