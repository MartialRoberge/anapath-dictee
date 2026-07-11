"""Moteur distant Gilbert (Lexia) — meeting-intelligence applique au CR ACP.

Gilbert fait STT + synthese cote serveur, de facon ASYNCHRONE : on televerse
l'audio, on attend la transcription, puis la synthese (generee selon un template
configure cote Lexia). Ce moteur implemente le meme protocole ``ReportEngine``
que le moteur local, ce qui permet de basculer sans toucher au code metier.

Etat de l'API Gilbert au moment de l'ecriture (v1.1.0, audit 07/2026) :
* ``POST /meetings/upload`` n'accepte que ``file`` + ``title`` — PAS encore de
  ``template_id`` ni de prompt. La selection de template se fait cote compte Lexia.
* ``GET /meetings/{id}/summary`` renvoie un markdown, pas le JSON structure
  {cr, organe, type_prelevement, alertes} attendu ici.

Consequence : ce moteur est fonctionnel pour transcrire, et sa methode
``generate`` mappe la synthese Gilbert vers ``GeneratedReport``. Les deux points
d'evolution attendus cote Gilbert (``template_id`` a l'upload + sortie
structuree) sont isoles et signales par ``GilbertCapabilityMissing``.
Voir docs/INTEGRATION_GILBERT.md pour la liste complete a mettre en place.
"""

from __future__ import annotations

import asyncio
import logging

import httpx

from config import Settings, get_settings
from reports.engine import (
    EngineCapabilities,
    GeneratedReport,
    ReportEngine,
    Transcript,
)

logger = logging.getLogger("anapath.engine.gilbert")

GILBERT_BASE_URL: str = "https://gilbert-assistant.ovh/api/v1"


class GilbertCapabilityMissing(RuntimeError):
    """Une capacite Gilbert requise n'est pas encore exposee par l'API."""


class GilbertReportEngine:
    """Implementation ``ReportEngine`` sur l'API Gilbert (asynchrone)."""

    capabilities = EngineCapabilities(
        name="gilbert",
        separate_transcription=True,
        is_async=True,
        supports_templates=True,  # via template configure cote Lexia
        supports_iteration=False,  # pas d'endpoint d'iteration cote Gilbert
    )

    def __init__(
        self,
        api_key: str,
        settings: Settings,
        *,
        base_url: str = GILBERT_BASE_URL,
        poll_interval: float = 3.0,
        poll_timeout: float = 300.0,
        gilbert_template_id: str | None = None,
    ) -> None:
        self._api_key = api_key
        self._settings = settings
        self._poll_interval = poll_interval
        self._poll_timeout = poll_timeout
        self._gilbert_template_id = gilbert_template_id
        self._client = httpx.AsyncClient(
            base_url=base_url,
            timeout=settings.stt_timeout_seconds,
            headers={"Authorization": f"Bearer {api_key}"},
        )

    @classmethod
    def build(cls) -> "GilbertReportEngine":
        settings = get_settings()
        return cls(
            api_key=getattr(settings, "gilbert_api_key", "") or "",
            settings=settings,
        )

    # -- Transcription : upload + polling ---------------------------------

    async def transcribe(self, audio_bytes: bytes, filename: str) -> Transcript:
        meeting_id: str = await self._upload(audio_bytes, filename)
        text: str = await self._poll_transcript(meeting_id)
        return Transcript(text=text, provider="gilbert")

    async def _upload(self, audio_bytes: bytes, filename: str) -> str:
        data: dict[str, str] = {"title": filename}
        # Point d'injection futur : quand Gilbert acceptera un template a l'upload,
        # ajouter ici data["template_id"] = self._gilbert_template_id.
        resp = await self._client.post(
            "/meetings/upload",
            files={"file": (filename, audio_bytes)},
            data=data,
        )
        resp.raise_for_status()
        payload = resp.json()
        meeting_id = payload.get("id") or payload.get("meeting_id")
        if not isinstance(meeting_id, str):
            raise GilbertCapabilityMissing(
                "Reponse d'upload Gilbert sans identifiant de meeting."
            )
        return meeting_id

    async def _poll_transcript(self, meeting_id: str) -> str:
        waited: float = 0.0
        while waited < self._poll_timeout:
            resp = await self._client.get(f"/meetings/{meeting_id}/transcript")
            resp.raise_for_status()
            data = resp.json()
            status = data.get("transcript_status")
            if status == "completed":
                text = data.get("transcript_text")
                return text if isinstance(text, str) else ""
            if status == "error":
                raise GilbertCapabilityMissing(
                    f"Transcription Gilbert en erreur (meeting {meeting_id})."
                )
            await asyncio.sleep(self._poll_interval)
            waited += self._poll_interval
        raise TimeoutError(
            f"Transcription Gilbert non terminee apres {self._poll_timeout}s."
        )

    # -- Generation : recuperation de la synthese -------------------------

    async def generate(
        self,
        transcript: str,
        *,
        rapport_precedent: str = "",
    ) -> GeneratedReport:
        """Genere un CR via la synthese Gilbert.

        Limite actuelle : l'API Gilbert renvoie un markdown libre, pas le JSON
        structure attendu. Tant que ce n'est pas expose, on ne peut pas garantir
        le contrat {cr, organe, type_prelevement, alertes} : on leve une erreur
        explicite plutot que de produire une sortie non fiable.
        """
        raise GilbertCapabilityMissing(
            "La generation structuree par template n'est pas encore exposee par "
            "l'API Gilbert (summary = markdown libre). Voir "
            "docs/INTEGRATION_GILBERT.md, section 'sortie structuree'. "
            "Utiliser LLM_PROVIDER=mistral / REPORT_ENGINE=local en attendant."
        )

    async def iterate(
        self, rapport_actuel: str, nouveau_transcript: str
    ) -> GeneratedReport:
        raise GilbertCapabilityMissing(
            "Gilbert n'expose pas d'endpoint d'iteration sur une synthese existante."
        )

    async def _map_summary_to_report(
        self, summary_markdown: str, transcript: str
    ) -> GeneratedReport:
        """Mappe une synthese markdown Gilbert vers GeneratedReport.

        Prevu pour le jour ou Gilbert renverra une synthese exploitable : la
        structure/organe seront deduits, les guardrails locaux (garde-chiffres,
        negations, recommandation hors contexte) restant applicables sur la sortie
        distante via ``build_validated_report``.
        """
        from reports.knowledge import build_context_block

        organes = build_context_block(transcript).organes
        return GeneratedReport(
            cr=summary_markdown,
            organe="non_determine",
            type_prelevement="autre",
            organes_detectes=organes,
            provider="gilbert",
            model="gilbert",
        )

    async def aclose(self) -> None:
        await self._client.aclose()


_: type[ReportEngine] = GilbertReportEngine
