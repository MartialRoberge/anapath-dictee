"""Gestion de la negation — SOURCE UNIQUE.

La codification (ADICAP, SNOMED) et la detection de contexte ne doivent JAMAIS
coder une lesion enoncee sous une negation ("absence de tumeur", "pas de
malignite"). Ce module centralise la liste des marqueurs de negation et le
masquage de la clause niee, jusqu'ici reimplementes dans adicap.py et snomed.py.
"""

from __future__ import annotations

# Marqueurs introduisant une clause de negation (texte deja normalise attendu).
NEGATION_MARKERS: tuple[str, ...] = (
    "absence de", "pas de", "sans ", "il n'est pas", "ne montre pas de",
    "ne trouve pas de", "indemne de", "il n'y a pas", "ni de",
)

# Separateurs qui referment une clause de negation (fin de la portee du masque).
_CLAUSE_SEPARATORS: tuple[str, ...] = (".", "\n", ";")


def mask_negations(texte: str, markers: tuple[str, ...] = NEGATION_MARKERS) -> str:
    """Remplace par des espaces chaque clause de negation (du marqueur jusqu'au
    prochain separateur de clause), en preservant les positions du reste du texte.

    Ainsi "adenocarcinome, absence de metastase." conserve "adenocarcinome" mais
    masque "absence de metastase" : un mot-cle recherche apres coup ne peut plus
    matcher dans la portion niee.
    """
    resultat: str = texte
    for marker in markers:
        while marker in resultat:
            pos: int = resultat.find(marker)
            end: int = len(resultat)
            for sep in _CLAUSE_SEPARATORS:
                sep_pos: int = resultat.find(sep, pos + len(marker))
                if sep_pos != -1 and sep_pos < end:
                    end = sep_pos
            resultat = resultat[:pos] + " " * (end - pos) + resultat[end:]
    return resultat
