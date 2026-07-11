"""Fixtures partagees : faux fournisseur LLM, faux moteur, client API.

Aucun test ne touche le reseau : les fournisseurs LLM/STT sont remplaces par
des doubles deterministes.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

import pytest

from config import Settings
from llm.base import LLMRequest, LLMResponse
from reports.engine import EngineCapabilities, GeneratedReport, Transcript
from reports.local_engine import LocalReportEngine


@dataclass
class FakeProvider:
    """Fournisseur LLM factice : renvoie un JSON pre-defini et memorise l'appel."""

    payload: dict[str, object]
    name: str = "fake"
    model: str = "fake-1"
    truncated: bool = False
    calls: list[LLMRequest] = field(default_factory=list)

    async def complete(self, request: LLMRequest) -> LLMResponse:
        self.calls.append(request)
        return LLMResponse(
            text=json.dumps(self.payload, ensure_ascii=False),
            model=self.model,
            provider=self.name,
            truncated=self.truncated,
        )

    async def aclose(self) -> None:
        return None


@dataclass
class FakeEngine:
    """Moteur factice pour les tests d'API (pas de LLM, pas de STT)."""

    report: GeneratedReport
    transcript_text: str = "transcript factice"
    capabilities: EngineCapabilities = field(
        default_factory=lambda: EngineCapabilities(
            name="fake",
            separate_transcription=True,
            is_async=False,
            supports_templates=True,
            supports_iteration=True,
        )
    )

    async def transcribe(self, audio_bytes: bytes, filename: str) -> Transcript:
        return Transcript(text=self.transcript_text, provider="fake")

    async def generate(self, transcript, *, rapport_precedent="") -> GeneratedReport:
        return self.report

    async def iterate(self, rapport_actuel, nouveau_transcript) -> GeneratedReport:
        return self.report

    async def aclose(self) -> None:
        return None


def make_report(**overrides) -> GeneratedReport:
    """Construit un GeneratedReport de test avec valeurs par defaut."""
    base = dict(
        cr="**__BIOPSIE PULMONAIRE__**\n**Microscopie :**\nAdenocarcinome.\n"
        "**__CONCLUSION :__**\n**Adenocarcinome infiltrant.**",
        organe="poumon",
        type_prelevement="biopsie",
        organes_detectes=["poumon"],
        provider="fake",
        model="fake-1",
    )
    base.update(overrides)
    return GeneratedReport(**base)


@pytest.fixture
def fake_settings() -> Settings:
    return Settings(
        llm_provider="mistral",
        mistral_api_key="test-key",
        llm_max_retries=1,
        jwt_secret="test-secret-value-at-least-32-characters-long",
    )


@pytest.fixture
def local_engine_factory(fake_settings):
    """Retourne une fabrique de LocalReportEngine avec un FakeProvider donne."""

    def _make(payload: dict[str, object], truncated: bool = False):
        provider = FakeProvider(payload=payload, truncated=truncated)
        engine = LocalReportEngine(provider=provider, settings=fake_settings)
        return engine, provider

    return _make
