"""Moteur MULTI-PASSES : comprendre -> rediger -> relire (un seul modele).

Meme socle que ``LocalReportEngine`` (STT, provider, guardrails de securite), mais
la generation est decomposee en 3 passes LLM a role explicite, ce qui apporte
l'EXPLICABILITE (on montre ce que le moteur a compris et ce que la relecture
signale) sans changer le contrat : renvoie un ``GeneratedReport`` (avec `trace`).

Plus lent (3 appels LLM au lieu d'1) — choix assume : qualite + transparence.
"""

from __future__ import annotations

import logging

from reports.engine import EngineCapabilities, GeneratedReport, ReportEngine
from reports.guardrails import GenerationParseError, build_validated_report, parse_llm_json
from reports.knowledge import ContextResult, build_context_block
from reports.local_engine import LocalReportEngine
from reports.prompts import build_format_system_prompt, build_format_user_prompt
from reports.prompts_multipass import (
    build_comprehension_hint,
    build_comprehension_system_prompt,
    build_comprehension_user_prompt,
    build_relecture_system_prompt,
    build_relecture_user_prompt,
)

logger = logging.getLogger("anapath.engine.multipass")

_CATEGORIE_LABEL: dict[str, str] = {
    "fidelite": "Fidélité",
    "manque": "Donnée manquante",
    "incertitude": "À vérifier",
    "coherence": "Cohérence",
}


class MultiPassReportEngine(LocalReportEngine):
    """Génération en 3 passes explicites, sur le socle local."""

    capabilities = EngineCapabilities(
        name="multipass",
        separate_transcription=True,
        is_async=False,
        supports_templates=True,
        supports_iteration=True,
    )

    async def generate(
        self, transcript: str, *, rapport_precedent: str = ""
    ) -> GeneratedReport:
        # --- Passe 1 : COMPREHENSION (adaptable, explicable) --------------
        comprehension = await self._comprehend(transcript)

        # Ressources metier deterministes (INCa, formulations maison) : inchangees.
        context: ContextResult = build_context_block(transcript)
        logger.info(
            "multipass: organes(det)=%s | organes(compris)=%s",
            context.organes, comprehension.get("organes"),
        )

        # --- Passe 2 : REDACTION -----------------------------------------
        system_prompt: str = build_format_system_prompt(context.block)
        user_prompt: str = (
            build_comprehension_hint(comprehension)
            + build_format_user_prompt(transcript, rapport_precedent)
        )
        raw: str = await self._complete(system_prompt, user_prompt, label="redaction")
        report: GeneratedReport = build_validated_report(
            raw,
            source_text=transcript,
            organes=context.organes,
            provider=self._provider.name,
            model=self._provider.model,
        )

        # --- Passe 3 : RELECTURE (signale, ne reecrit pas) ---------------
        signalements = await self._review(report.cr, transcript)

        # Les signalements de relecture rejoignent les warnings (canal deja
        # remonte au front) et la trace d'explicabilite.
        report.warnings = report.warnings + [
            f"Relecture — {_CATEGORIE_LABEL.get(str(s.get('categorie')), 'Note')} : "
            f"{s.get('message', '')}"
            for s in signalements
        ]
        report.trace = {
            "comprehension": comprehension,
            "signalements": signalements,
            "passes": [
                {"role": "comprehension", "model": self._provider.model},
                {"role": "redaction", "model": self._provider.model},
                {"role": "relecture", "model": self._provider.model},
            ],
        }
        return report

    # -- Passes annexes (degradation gracieuse : jamais bloquantes) --------

    async def _comprehend(self, transcript: str) -> dict[str, object]:
        """Passe 1. Retourne {} si la comprehension echoue (on continue sans)."""
        try:
            raw = await self._complete(
                build_comprehension_system_prompt(),
                build_comprehension_user_prompt(transcript),
                label="comprehension",
            )
            data = parse_llm_json(raw)
            return data if isinstance(data, dict) else {}
        except (GenerationParseError, ValueError, Exception) as exc:  # noqa: BLE001
            logger.warning("comprehension ignoree : %s", exc)
            return {}

    async def _review(self, cr: str, transcript: str) -> list[dict[str, object]]:
        """Passe 3. Retourne [] si la relecture echoue (on continue sans)."""
        try:
            raw = await self._complete(
                build_relecture_system_prompt(),
                build_relecture_user_prompt(cr, transcript),
                label="relecture",
            )
            data = parse_llm_json(raw)
            items = data.get("signalements") if isinstance(data, dict) else None
            if not isinstance(items, list):
                return []
            return [s for s in items if isinstance(s, dict) and s.get("message")]
        except (GenerationParseError, ValueError, Exception) as exc:  # noqa: BLE001
            logger.warning("relecture ignoree : %s", exc)
            return []


_: type[ReportEngine] = MultiPassReportEngine
