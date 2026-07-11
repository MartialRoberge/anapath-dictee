"""Moteur de generation de comptes-rendus.

L'abstraction centrale est ``ReportEngine`` : un moteur transforme une dictee
(audio ou transcript) en compte-rendu structure, en s'appuyant sur un template
metier. Deux implementations coexistent derriere la meme interface :

* ``LocalReportEngine`` — pipeline actuel : STT Voxtral + LLM (Mistral par
  defaut) applique un template rendu en prompt (slot-filling). Synchrone.
* ``GilbertReportEngine`` — moteur distant type Gilbert : upload audio +
  template_id, la synthese est generee cote Lexia. Asynchrone. (Design pret,
  activable via configuration quand l'API Gilbert exposera la generation par
  template — voir docs/INTEGRATION_GILBERT.md.)

Le reste de l'application (routes FastAPI) ne depend que de ``ReportEngine`` et
des types ``Transcript`` / ``GeneratedReport``.
"""

from reports.engine import (
    EngineCapabilities,
    GeneratedReport,
    ReportEngine,
    Transcript,
)
from reports.factory import get_report_engine, reset_report_engine

__all__ = [
    "EngineCapabilities",
    "GeneratedReport",
    "ReportEngine",
    "Transcript",
    "get_report_engine",
    "reset_report_engine",
]
