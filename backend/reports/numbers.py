"""Normalisation des nombres francais parles vers des chiffres.

Sert au guardrail anti-hallucination : la dictee vocale enonce les nombres en
toutes lettres ("cinq millimetres", "dix-huit"), le CR les ecrit en chiffres
("5 mm", "18"). Pour verifier qu'un chiffre du CR provient bien de la dictee, on
convertit les nombres ecrits en lettres de la dictee en chiffres, puis on
compare.
"""

from __future__ import annotations

import re

_UNITS: dict[str, int] = {
    "zero": 0, "un": 1, "une": 1, "deux": 2, "trois": 3, "quatre": 4,
    "cinq": 5, "six": 6, "sept": 7, "huit": 8, "neuf": 9, "dix": 10,
    "onze": 11, "douze": 12, "treize": 13, "quatorze": 14, "quinze": 15,
    "seize": 16, "dix-sept": 17, "dix-huit": 18, "dix-neuf": 19,
    "vingt": 20, "trente": 30, "quarante": 40, "cinquante": 50,
    "soixante": 60, "quatre-vingt": 80, "quatre-vingts": 80, "cent": 100,
    "cents": 100, "mille": 1000,
}

# Multiplicatifs simples pour les dizaines composees (vingt-et-un, trente-deux...)
_TENS: dict[str, int] = {
    "vingt": 20, "trente": 30, "quarante": 40, "cinquante": 50,
    "soixante": 60, "quatre-vingt": 80, "quatre-vingts": 80,
}

_NUMBER_TOKEN: re.Pattern[str] = re.compile(r"[a-zàâäéèêëîïôöùûüç]+", re.IGNORECASE)


def _word_to_int(phrase: str) -> int | None:
    """Convertit une expression francaise (0-999) en entier, ou None."""
    phrase = phrase.strip().lower().replace("et-", "").replace(" et ", "-")
    phrase = phrase.replace(" ", "-")
    if not phrase:
        return None

    if phrase in _UNITS:
        return _UNITS[phrase]

    # dizaine-unite : "trente-deux", "quatre-vingt-quatre", "soixante-douze"
    parts: list[str] = phrase.split("-")
    total: int = 0
    i: int = 0
    matched: bool = False
    while i < len(parts):
        # tente "quatre-vingt" (deux tokens)
        two = "-".join(parts[i : i + 2])
        if two in _TENS:
            total += _TENS[two]
            i += 2
            matched = True
            continue
        tok = parts[i]
        if tok in _TENS:
            total += _TENS[tok]
            i += 1
            matched = True
            continue
        if tok in _UNITS:
            total += _UNITS[tok]
            i += 1
            matched = True
            continue
        return None
    return total if matched else None


def spelled_numbers_to_digits(text: str) -> set[str]:
    """Extrait les nombres ecrits en lettres et renvoie leurs formes chiffrees.

    Balaye des fenetres glissantes de 1 a 4 mots pour capter "quatre-vingt-quatre".
    """
    tokens: list[str] = _NUMBER_TOKEN.findall(text.lower())
    found: set[str] = set()
    n: int = len(tokens)
    for i in range(n):
        for window in range(4, 0, -1):
            if i + window > n:
                continue
            phrase: str = "-".join(tokens[i : i + window])
            value: int | None = _word_to_int(phrase)
            if value is not None:
                found.add(str(value))
    return found


_DIGIT_RUN: re.Pattern[str] = re.compile(r"\d+")


def digits_in(text: str) -> list[str]:
    """Liste des suites de chiffres presentes dans un texte."""
    return _DIGIT_RUN.findall(text)


def source_number_set(source_text: str) -> set[str]:
    """Ensemble des nombres presents dans la dictee, sous forme chiffree.

    Combine les chiffres litteraux et les nombres ecrits en toutes lettres.
    """
    numbers: set[str] = set(digits_in(source_text))
    numbers |= spelled_numbers_to_digits(source_text)
    return numbers
