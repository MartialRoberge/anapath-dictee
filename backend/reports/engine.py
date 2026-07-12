"""Types et protocole du moteur de compte-rendu."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

from models import DonneeManquante
from specimen_type import SpecimenType


@dataclass(frozen=True, slots=True)
class EngineCapabilities:
    """Capacites declarees d'un moteur — l'API s'y adapte."""

    name: str
    #: Le moteur expose une etape de transcription separee (transcript editable
    #: avant generation). Faux pour un moteur qui fait STT+synthese en un bloc.
    separate_transcription: bool
    #: Generation asynchrone (upload -> polling/webhook) vs synchrone.
    is_async: bool
    #: Applique des templates metier.
    supports_templates: bool
    #: Sait integrer une dictee complementaire a un CR existant.
    supports_iteration: bool


@dataclass(frozen=True, slots=True)
class Transcript:
    """Resultat de transcription (STT)."""

    text: str
    language: str = "fr"
    confidence: float | None = None
    provider: str = ""


@dataclass(slots=True)
class GeneratedReport:
    """Compte-rendu structure produit par un moteur."""

    cr: str
    organe: str
    type_prelevement: str
    alertes: list[DonneeManquante] = field(default_factory=list)
    #: Avertissements guardrails (non bloquants) : negations a verifier,
    #: chiffres non retrouves dans la dictee, recommandation hors contexte, etc.
    warnings: list[str] = field(default_factory=list)
    #: Organes detectes automatiquement dans la dictee (0, 1 ou plusieurs).
    organes_detectes: list[str] = field(default_factory=list)
    #: Verdict de coherence medicale (structure/coherence interne), calcule a
    #: CHAQUE generation. Voir reports/coherence.py.
    coherence: dict[str, object] = field(default_factory=dict)
    provider: str = ""
    model: str = ""

    @property
    def specimen(self) -> SpecimenType:
        return SpecimenType.from_str(self.type_prelevement)


@runtime_checkable
class ReportEngine(Protocol):
    """Contrat d'un moteur de generation de compte-rendu."""

    capabilities: EngineCapabilities

    async def transcribe(self, audio_bytes: bytes, filename: str) -> Transcript:
        """Transcrit un audio en texte brut (STT)."""
        ...

    async def generate(
        self,
        transcript: str,
        *,
        rapport_precedent: str = "",
    ) -> GeneratedReport:
        """Genere un CR structure a partir d'un transcript (organe auto-detecte)."""
        ...

    async def iterate(
        self, rapport_actuel: str, nouveau_transcript: str
    ) -> GeneratedReport:
        """Integre une dictee complementaire dans un CR existant."""
        ...

    async def aclose(self) -> None:
        """Libere les ressources (clients HTTP)."""
        ...
