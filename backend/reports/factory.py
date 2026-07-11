"""Selection du moteur de compte-rendu actif depuis la configuration."""

from __future__ import annotations

from config import get_settings
from reports.engine import ReportEngine

_engine_singleton: ReportEngine | None = None


def build_report_engine() -> ReportEngine:
    """Construit le moteur selon ``settings.report_engine`` (local | gilbert)."""
    name: str = get_settings().report_engine.strip().lower()

    if name == "local":
        from reports.local_engine import LocalReportEngine

        return LocalReportEngine.build()

    if name == "gilbert":
        from reports.gilbert_engine import GilbertReportEngine

        return GilbertReportEngine.build()

    raise ValueError(
        f"Moteur de compte-rendu inconnu : '{name}'. Valeurs : local, gilbert."
    )


def get_report_engine() -> ReportEngine:
    """Retourne le moteur de compte-rendu actif (singleton)."""
    global _engine_singleton
    if _engine_singleton is None:
        _engine_singleton = build_report_engine()
    return _engine_singleton


def reset_report_engine() -> ReportEngine | None:
    """Reinitialise le singleton (tests). Retourne l'ancien moteur a fermer."""
    global _engine_singleton
    previous = _engine_singleton
    _engine_singleton = None
    return previous
