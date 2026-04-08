"""Utilitaires de traitement de texte partages entre les modules.

Fournit la normalisation de texte (suppression des accents, minuscules)
utilisee par tous les modules de detection et de codage.
"""


def normaliser(texte: str) -> str:
    """Normalise le texte pour la recherche de mots-cles.

    Convertit en minuscules et remplace les caracteres accentues
    par leurs equivalents non-accentues.
    """
    resultat: str = texte.lower()
    remplacements: dict[str, str] = {
        "é": "e", "è": "e", "ê": "e", "ë": "e",
        "à": "a", "â": "a", "ä": "a",
        "ù": "u", "û": "u", "ü": "u",
        "ô": "o", "ö": "o",
        "î": "i", "ï": "i",
        "ç": "c", "œ": "oe",
    }
    for accent, remplacement in remplacements.items():
        resultat = resultat.replace(accent, remplacement)
    return resultat
