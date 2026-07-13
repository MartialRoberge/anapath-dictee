"""Normalisation de texte — SOURCE UNIQUE pour tout le backend.

Tous les modules de detection, de codification et de garde-fous comparent des
mots-cles a du texte libre : ils doivent le faire avec la MEME normalisation,
sinon un accent ou une ligature suffit a manquer une correspondance. Ce module
est l'unique implementation ; aucun autre fichier ne doit re-coder un
`strip_accents` / `_norm` local.

Trois niveaux, du moins au plus agressif :
- ``strip_accents`` : retire les diacritiques, conserve la casse et les espaces ;
- ``normaliser``    : minuscule + sans accents (cle de recherche de mots-cles) ;
- ``cle_alphanum``  : minuscule + sans accents + caracteres alphanumeriques seuls
  (cle de deduplication, insensible a la ponctuation et aux espaces).
"""

from __future__ import annotations

import unicodedata

# Ligatures que la decomposition NFD ne separe PAS (elle les laisserait tomber
# a l'encodage ASCII) : on les developpe explicitement pour ne pas perdre, par
# exemple, le "oe" de "oesophage".
_LIGATURES: dict[str, str] = {
    "œ": "oe", "Œ": "OE", "æ": "ae", "Æ": "AE", "ß": "ss",
}


def strip_accents(texte: str) -> str:
    """Retire accents et diacritiques en conservant la casse et les espaces.

    Developpe d'abord les ligatures francaises (œ→oe, æ→ae) puis supprime les
    marques combinantes via la decomposition Unicode NFD.
    """
    for ligature, remplacement in _LIGATURES.items():
        texte = texte.replace(ligature, remplacement)
    decomposition = unicodedata.normalize("NFD", texte)
    return "".join(c for c in decomposition if not unicodedata.combining(c))


def normaliser(texte: str) -> str:
    """Minuscule et sans accents — cle de recherche de mots-cles standard."""
    return strip_accents(texte).lower()


def cle_alphanum(texte: str) -> str:
    """Cle de deduplication : minuscule, sans accents, alphanumerique seul.

    "pT3, pN1 (8e ed.)" et "ptnm" partagent ainsi une base comparable.
    """
    return "".join(c for c in normaliser(texte) if c.isalnum())
