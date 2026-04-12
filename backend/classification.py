"""Parsing defensif de la classification retournee par Claude.

Depuis la v5, la classification est produite dans le meme appel Claude
que le CRDocument (voir ``agent.py``). Ce module ne contient plus
d'appel API, uniquement le parsing JSON -> Classification typee.

Convention : une fonction = une action. Tout est defensif : JSON
invalide -> Classification generique avec confidence 0.
"""

from __future__ import annotations

import json
from typing import cast

from schemas import Classification, ClassificationCandidate, Organe


# ---------------------------------------------------------------------------
# Organes valides
# ---------------------------------------------------------------------------


_ORGANES_VALIDES: set[str] = {
    "poumon", "sein", "digestif", "gynecologie", "urologie",
    "orl", "dermatologie", "hematologie", "os_articulations",
    "tissus_mous", "neurologie", "ophtalmologie",
    "cardiovasculaire", "endocrinologie", "generic",
}


# ---------------------------------------------------------------------------
# Fonctions de coercition
# ---------------------------------------------------------------------------


def _coerce_organe(raw: object) -> Organe:
    """Normalise une valeur en Organe valide, fallback generic."""
    if isinstance(raw, str) and raw in _ORGANES_VALIDES:
        return cast(Organe, raw)
    return "generic"


def _clamp_confidence(value: object) -> float:
    """Garantit que la confidence est un float dans [0, 1]."""
    try:
        f: float = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0.0
    return max(0.0, min(1.0, f))


def _fallback_candidate() -> ClassificationCandidate:
    """Candidat generique de secours si le JSON est invalide."""
    return ClassificationCandidate(
        organe="generic",
        sous_type="inconnu",
        est_carcinologique=False,
        diagnostic_presume="non classifie",
        confidence=0.0,
    )


def _coerce_candidate(raw: object) -> ClassificationCandidate:
    """Convertit un dict brut en ClassificationCandidate avec valeurs par defaut."""
    if not isinstance(raw, dict):
        return _fallback_candidate()
    data: dict[str, object] = raw

    return ClassificationCandidate(
        organe=_coerce_organe(data.get("organe")),
        sous_type=str(data.get("sous_type", "inconnu") or "inconnu"),
        est_carcinologique=bool(data.get("est_carcinologique", False)),
        diagnostic_presume=str(data.get("diagnostic_presume", "") or ""),
        confidence=_clamp_confidence(data.get("confidence", 0.0)),
    )


# ---------------------------------------------------------------------------
# API publique
# ---------------------------------------------------------------------------


def parse_classification_json(
    raw_text: str, transcript_normalise: str
) -> Classification:
    """Decode une reponse JSON en Classification typee.

    Tolere les reponses mal formees : retourne une classification
    ``generic`` avec confidence 0 plutot que de lever.
    """
    try:
        data = json.loads(raw_text)
    except json.JSONDecodeError:
        return Classification(
            top=_fallback_candidate(),
            alternative=None,
            transcript_normalise=transcript_normalise,
        )

    if not isinstance(data, dict):
        return Classification(
            top=_fallback_candidate(),
            alternative=None,
            transcript_normalise=transcript_normalise,
        )

    top_raw: object = data.get("top", {})
    alt_raw: object = data.get("alternative")

    top: ClassificationCandidate = _coerce_candidate(top_raw)
    alternative: ClassificationCandidate | None = (
        _coerce_candidate(alt_raw) if isinstance(alt_raw, dict) else None
    )

    return Classification(
        top=top,
        alternative=alternative,
        transcript_normalise=transcript_normalise,
    )
