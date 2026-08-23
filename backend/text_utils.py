"""Normalisation de texte — SOURCE UNIQUE pour tout le backend.

Tous les modules de detection, de codification et de garde-fous comparent des
mots-cles a du texte libre : ils doivent le faire avec la MEME normalisation,
sinon un accent ou une ligature suffit a manquer une correspondance. Ce module
est l'unique implementation ; aucun autre fichier ne doit re-coder un
`strip_accents` / `_norm` local.

Trois niveaux, du moins au plus agressif :
- ``strip_accents`` : replie ponctuation et diacritiques, conserve la casse ;
- ``normaliser``    : minuscule + strip_accents (cle de recherche de mots-cles) ;
- ``cle_alphanum``  : minuscule + sans accents + caracteres alphanumeriques seuls
  (cle de deduplication, insensible a la ponctuation et aux espaces).

Le repli ne preserve pas la longueur : la ligature oe entre sur un caractere et
sort sur deux, U+2026 sort sur trois, U+00AD disparait. Aucun appelant ne doit
donc reporter un offset calcule sur le texte normalise vers le texte d'origine :
on normalise APRES avoir repere les positions, jamais l'inverse.
"""

from __future__ import annotations

import unicodedata

# Ligatures que la decomposition NFD ne separe PAS (elle les laisserait tomber
# a l'encodage ASCII) : on les developpe explicitement pour ne pas perdre, par
# exemple, le "oe" de "oesophage".
_LIGATURES: dict[str, str] = {
    "œ": "oe", "Œ": "OE", "æ": "ae", "Æ": "AE", "ß": "ss",
}

# Ponctuation typographique repliee sur la forme que tape un clavier.
#
# Un compte rendu colle depuis Word ou depuis un navigateur porte des
# apostrophes courbes, des tirets cadratins et des points de suspension la ou le
# praticien qui dicte ou qui frappe produit l'apostrophe droite, le trait
# d'union et trois points. Sans ce repli la comparaison echoue SANS ERREUR et
# SANS RESULTAT, ce qui est le pire des echecs : rien ne signale la perte.
#
# Le cas qui a motive la regle : dans le thesaurus ADICAP officiel, 766 libelles
# ecrivent l'apostrophe droite et exactement UN (SGSE, "GANGLIONS ... DE
# L'ABDOMEN") la courbe. Ce concept etait donc introuvable a la frappe normale.
# Le libelle X4M0 pose le meme probleme avec les points de suspension U+2026.
_PONCTUATION: dict[str, str] = {
    # Apostrophes et quotes simples
    "‘": "'", "’": "'", "‛": "'",
    "′": "'", "´": "'", "ʼ": "'",
    # Guillemets doubles, anglais et francais
    "“": '"', "”": '"', "„": '"', "‟": '"',
    "″": '"', "«": '"', "»": '"',
    # Tirets : demi-cadratin, cadratin, insecable, signe moins
    "‐": "-", "‑": "-", "‒": "-",
    "–": "-", "—": "-", "―": "-", "−": "-",
    # Points de suspension
    "…": "...",
}

# Toutes les espaces Unicode (categorie Zs) se replient sur l'espace ASCII.
# Word et le HTML sement des insecables (U+00A0) et des fines (U+202F) la ou le
# clavier tape une espace ordinaire ; "de haut grade" avec une insecable ne
# repond alors a aucun mot-cle. Les enumerer a la main serait incomplet, donc on
# les derive de la table Unicode : les 17 caracteres Zs tiennent sous U+3000.
_ESPACES: dict[str, str] = {
    chr(point): " "
    for point in range(0x3000 + 1)
    if unicodedata.category(chr(point)) == "Zs"
}

# Caracteres de formatage invisibles (categorie Cf) : cesure conditionnelle de
# Word (U+00AD), largeurs nulles, BOM colle en tete de fichier. Ils ne se voient
# pas mais coupent un mot en deux pour toute comparaison, donc on les efface.
_INVISIBLES: dict[str, str] = {
    chr(point): ""
    for point in range(0xFEFF + 1)
    if unicodedata.category(chr(point)) == "Cf"
}

# Une seule table de traduction pour les quatre replis : un unique parcours de
# la chaine, et aucun ordre d'application a raisonner.
_TABLE_REPLI: dict[int, str] = str.maketrans(
    {**_LIGATURES, **_PONCTUATION, **_ESPACES, **_INVISIBLES}
)


def _replier_ascii(texte: str) -> str:
    """Replie ligatures, ponctuation typographique, espaces et invisibles."""
    return texte.translate(_TABLE_REPLI)


def _retirer_diacritiques(texte: str) -> str:
    """Supprime les marques combinantes via la decomposition Unicode NFD."""
    decomposition = unicodedata.normalize("NFD", texte)
    return "".join(c for c in decomposition if not unicodedata.combining(c))


def strip_accents(texte: str) -> str:
    """Rend le texte a sa forme ASCII, casse et espaces conserves.

    Deux ecritures d'un meme mot — accentuee ou non, avec apostrophe courbe ou
    droite, avec espace insecable ou ordinaire — doivent produire la MEME
    chaine, sinon la comparaison de mots-cles rate en silence.
    """
    return _retirer_diacritiques(_replier_ascii(texte))


def normaliser(texte: str) -> str:
    """Minuscule et sans accents — cle de recherche de mots-cles standard."""
    return strip_accents(texte).lower()


def cle_alphanum(texte: str) -> str:
    """Cle de deduplication : minuscule, sans accents, alphanumerique seul.

    "pT3, pN1 (8e ed.)" et "ptnm" partagent ainsi une base comparable.
    """
    return "".join(c for c in normaliser(texte) if c.isalnum())
