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


#: Un nombre suivi de son unite ou de ce qu'il compte. C'est cette forme-la
#: qu'on verifie, et non tout chiffre du texte : un numero de bloc ou un rang
#: d'enumeration n'est pas une donnee clinique, et les signaler noierait les
#: chiffres qui, eux, engagent une decision.
_CHIFFRE_PORTEUR: re.Pattern[str] = re.compile(
    r"(\d+(?:[.,]\d+)?)\s*"
    r"(mm|cm|ml|mL|%|millimetre|centimetre|ganglion|mitose|bloc|fragment|"
    r"loge|plan de coupe)",
    re.IGNORECASE,
)

#: Une annee n'est pas une mesure : la citer sans qu'elle soit dictee est
#: banal (date de prelevement, antecedent) et n'a aucune portee clinique.
_ANNEE: re.Pattern[str] = re.compile(r"\b(?:19|20)\d{2}\b")

#: Numerotation STRUCTURELLE. Le pathologiste dicte rarement chaque numero de
#: bloc, et les signaler ferait du bruit sur ce qui n'est qu'un rangement.
_UNITES_STRUCTURELLES: frozenset[str] = frozenset({"bloc", "loge", "plan de coupe"})


def chiffres_non_dictes(texte: str, dictee: str) -> tuple[str, ...]:
    """Les chiffres porteurs du texte qui n'existent nulle part dans la dictee.

    POURQUOI CETTE FONCTION EXISTE, et pourquoi elle est PUBLIQUE.

    L'ancrage d'une assertion se fait sur les MOTS, et il a de bonnes raisons
    de ne pas se faire sur les chiffres : un "5 %" s'ancrait joyeusement sur un
    "5 mm" dicte trois phrases plus loin, ce qui declarait soutenue une
    assertion inventee. Les chiffres ont donc ete retires des ancres.

    Mais alors une phrase dont TOUS les mots sont dictes passe pour soutenue
    meme si son chiffre est invente. Mesure sur un vrai cas : la dictee enumere
    cinq ganglions peribronchiques, deux intraparenchymateux et trois
    sous-carinaires ; le compte rendu produit "0/22 ganglions examines". Chaque
    mot de cette phrase est dans la dictee. Le 22 ne l'est pas — et c'est lui
    qui dit si le curage est adequat.

    Le mot et le chiffre sont donc deux preuves DISTINCTES, et il faut les deux.
    Cette fonction porte la seconde, pour que le garde-fou du moteur et
    l'instrumentation de l'etude s'appuient sur la MEME definition : deux
    definitions concurrentes de "chiffre absent de la dictee" finiraient par
    diverger, et l'une des deux se tromperait sans qu'on sache laquelle.

    Les nombres ecrits en toutes lettres comptent comme dictes : "vingt-deux"
    soutient "22".
    """
    presents: set[str] = source_number_set(dictee)
    absents: list[str] = []
    vus: set[str] = set()

    for trouve in _CHIFFRE_PORTEUR.finditer(texte):
        brut: str = trouve.group(1)
        unite: str = trouve.group(2)
        contexte: str = trouve.group(0).strip()

        if _ANNEE.search(contexte):
            continue
        if unite.lower() in _UNITES_STRUCTURELLES:
            continue

        normalise: str = brut.replace(",", ".")
        if normalise in presents or normalise.split(".")[0] in presents:
            continue

        cle: str = f"{brut}:{unite.lower()}"
        if cle in vus:
            continue
        vus.add(cle)
        absents.append(contexte)

    return tuple(absents)
