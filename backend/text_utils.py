"""Utilitaires de traitement de texte partages entre les modules.

Fournit la normalisation de texte (suppression des accents, minuscules,
collapse des espaces) utilisee par validation, retrieval et codification.

Convention : une fonction = une action. Ce module est la SOURCE UNIQUE
pour toute normalisation de texte du pipeline.
"""

import unicodedata


_ACCENT_MAP: dict[str, str] = {
    "é": "e", "è": "e", "ê": "e", "ë": "e",
    "à": "a", "â": "a", "ä": "a",
    "ù": "u", "û": "u", "ü": "u",
    "ô": "o", "ö": "o",
    "î": "i", "ï": "i",
    "ç": "c", "œ": "oe", "æ": "ae",
}


def strip_accents(text: str) -> str:
    """Retire les accents et diacritiques francais courants.

    Conversion manuelle plutot que ``unicodedata.normalize('NFD')`` pour
    garder un controle total sur les remplacements (ex: ``œ`` -> ``oe``).
    """
    result: str = text
    for accent, plain in _ACCENT_MAP.items():
        result = result.replace(accent, plain)
    return result


def normaliser(texte: str) -> str:
    """Normalise le texte pour la recherche de mots-cles.

    Pipeline : NFC -> minuscules -> strip accents -> collapse whitespace.
    """
    normalized: str = unicodedata.normalize("NFC", texte)
    lowered: str = normalized.lower()
    stripped: str = strip_accents(lowered)
    return " ".join(stripped.split())
