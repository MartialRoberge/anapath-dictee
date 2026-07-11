"""Moteur local : STT Voxtral + LLM (Mistral par defaut) + détection auto + guardrails.

Pipeline synchrone en deux etapes exposees separement (transcribe puis generate).
La generation est ENTIEREMENT automatique : aucun choix de template par l'utilisateur.
Les organes sont detectes dans la dictee (multi-organes gere), et les connaissances
metier de chacun sont injectees de facon additive dans le prompt.
"""

from __future__ import annotations

import logging

from config import Settings, get_settings
from llm.base import LLMMessage, LLMProvider, LLMRequest
from llm.factory import get_llm_provider
from reports.engine import (
    EngineCapabilities,
    GeneratedReport,
    ReportEngine,
    Transcript,
)
from reports.guardrails import build_validated_report
from reports.knowledge import ContextResult, build_context_block
from reports.prompts import (
    build_format_system_prompt,
    build_format_user_prompt,
    build_iteration_system_prompt,
    build_iteration_user_prompt,
)
from reports.retry import with_retry
from transcription import transcribe_audio

logger = logging.getLogger("anapath.engine.local")


class LocalReportEngine:
    """Implementation ``ReportEngine`` sur infrastructure locale."""

    capabilities = EngineCapabilities(
        name="local",
        separate_transcription=True,
        is_async=False,
        supports_templates=True,
        supports_iteration=True,
    )

    def __init__(self, provider: LLMProvider, settings: Settings) -> None:
        self._provider = provider
        self._settings = settings

    @classmethod
    def build(cls) -> "LocalReportEngine":
        """Construit le moteur depuis la configuration globale."""
        return cls(provider=get_llm_provider(), settings=get_settings())

    # -- Etape 1 : transcription ------------------------------------------

    async def transcribe(self, audio_bytes: bytes, filename: str) -> Transcript:
        text: str = await transcribe_audio(audio_bytes, filename)
        return Transcript(text=text, provider="voxtral")

    # -- Etape 2 : generation (automatique) -------------------------------

    async def generate(
        self, transcript: str, *, rapport_precedent: str = ""
    ) -> GeneratedReport:
        context: ContextResult = build_context_block(transcript)
        logger.info(
            "generate: organes=%s | specimen=%s",
            context.organes, context.specimen.value,
        )

        system_prompt: str = build_format_system_prompt(context.block)
        user_prompt: str = build_format_user_prompt(transcript, rapport_precedent)
        raw: str = await self._complete(system_prompt, user_prompt, label="format")

        return build_validated_report(
            raw,
            source_text=transcript,
            organes=context.organes,
            provider=self._provider.name,
            model=self._provider.model,
        )

    async def iterate(
        self, rapport_actuel: str, nouveau_transcript: str
    ) -> GeneratedReport:
        system_prompt: str = build_iteration_system_prompt()
        user_prompt: str = build_iteration_user_prompt(
            rapport_actuel, nouveau_transcript
        )
        raw: str = await self._complete(system_prompt, user_prompt, label="iterate")

        # Le CR final fusionne l'ancien et le nouveau : le garde-chiffres compare
        # aux deux sources ; les organes sont re-detectes sur l'ensemble.
        source: str = f"{rapport_actuel}\n{nouveau_transcript}"
        organes = build_context_block(source).organes
        return build_validated_report(
            raw,
            source_text=source,
            organes=organes,
            provider=self._provider.name,
            model=self._provider.model,
        )

    # -- Appel LLM avec retry ---------------------------------------------

    async def _complete(
        self, system_prompt: str, user_prompt: str, *, label: str
    ) -> str:
        request = LLMRequest(
            system=system_prompt,
            messages=[LLMMessage(role="user", content=user_prompt)],
            temperature=self._settings.llm_temperature,
            max_tokens=self._settings.llm_max_tokens,
            json_object=True,
        )

        async def _call() -> str:
            response = await self._provider.complete(request)
            if response.truncated:
                raise ValueError(
                    "Le compte-rendu depasse la longueur maximale et a ete tronque. "
                    "Dictez en plusieurs parties via l'iteration."
                )
            return response.text

        return await with_retry(
            _call, max_retries=self._settings.llm_max_retries, label=label
        )

    async def aclose(self) -> None:
        await self._provider.aclose()


_: type[ReportEngine] = LocalReportEngine
