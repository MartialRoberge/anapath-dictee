"""Outils de texte du pipeline v3 : jetons avec offsets, localisation de citations.

Regle d'or (heritee de etude/ancrage.py) : on ne demande JAMAIS d'offsets a un
modele de langage. Le modele recopie une citation ; c'est ce module qui la
retrouve dans la dictee et calcule l'empan. Une citation introuvable n'a pas
d'empan : l'appelant la rejette ou baisse la confiance.

Les offsets pointent toujours vers le texte d'ORIGINE (accents compris), que le
frontend surligne. La normalisation s'applique jeton par jeton, apres reperage.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from etude.ancrage import Jeton, ancrer, decouper
from text_utils import normaliser

#: Decoupage en phrases : ponctuation forte ou retour a la ligne.
_FIN_PHRASE: re.Pattern[str] = re.compile(r"[^.;!?\n]+[.;!?]?")


@dataclass(frozen=True, slots=True)
class Localisation:
    """Empan d'une citation dans un texte, et la methode qui l'a trouve."""

    debut: int
    fin: int
    extrait: str
    #: "exacte" (suite de jetons identique) ou "ancrage" (recouvrement de jetons).
    methode: str


def jetons(texte: str) -> list[Jeton]:
    """Jetons normalises du texte, avec offsets dans le texte d'origine."""
    return decouper(texte)


def _formes_equivalentes(a: str, b: str) -> bool:
    """Egalite de jetons tolerante au pluriel simple (s/x final)."""
    if a == b:
        return True
    if len(a) > 3 and len(b) > 3:
        return a.rstrip("sx") == b.rstrip("sx")
    return False


def localiser_exacte(citation: str, texte: str, depuis: int = 0) -> Localisation | None:
    """Retrouve la citation comme suite CONTIGUE de jetons du texte.

    Insensible a la casse, aux accents, a la ponctuation et au pluriel simple.
    Retourne la premiere occurrence a partir de l'offset ``depuis``.
    """
    cibles = [j.forme for j in jetons(citation)]
    if not cibles:
        return None
    toks = [j for j in jetons(texte) if j.debut >= depuis]
    n = len(cibles)
    for i in range(len(toks) - n + 1):
        if all(_formes_equivalentes(toks[i + k].forme, cibles[k]) for k in range(n)):
            debut, fin = toks[i].debut, toks[i + n - 1].fin
            return Localisation(debut, fin, texte[debut:fin], "exacte")
    return None


def localiser(citation: str, texte: str, tolerante: bool = False) -> Localisation | None:
    """Localise une citation : exacte d'abord, puis (option) par ancrage.

    ``tolerante=False`` (extracteur) : seule la correspondance exacte compte, un
    fait dont la citation n'est pas dans la dictee est rejete.
    ``tolerante=True`` (redacteur/relecteur) : repli sur l'ancrage par
    recouvrement de jetons de etude/ancrage.py, deterministe.
    """
    if not citation or not citation.strip():
        return None
    trouve = localiser_exacte(citation, texte)
    if trouve is not None or not tolerante:
        return trouve
    empan = ancrer(citation, texte)
    if empan is None:
        return None
    return Localisation(empan.debut, empan.fin, empan.extrait, "ancrage")


def phrases(texte: str) -> list[tuple[int, int, str]]:
    """Decoupe en phrases (debut, fin, texte), offsets dans le texte d'origine."""
    res: list[tuple[int, int, str]] = []
    for m in _FIN_PHRASE.finditer(texte):
        brut = m.group(0)
        gauche = len(brut) - len(brut.lstrip())
        droite = len(brut.rstrip())
        if droite <= gauche:
            continue
        debut, fin = m.start() + gauche, m.start() + droite
        if re.search(r"\w", texte[debut:fin]):
            res.append((debut, fin, texte[debut:fin]))
    return res


def extrait_court(texte: str, limite: int = 200) -> str:
    """Citation courte (<= limite caracteres) pour SourceRef.extrait."""
    texte = " ".join(texte.split())
    return texte if len(texte) <= limite else texte[: limite - 1].rstrip() + "…"


def contient_terme(texte_normalise: str, terme: str) -> bool:
    """Le terme (normalise) apparait-il a limites de mots (pluriel s/x tolere) dans le texte normalise ?"""
    t = normaliser(terme).strip()
    if not t:
        return False
    return re.search(rf"(?<![a-z0-9]){re.escape(t)}(?:s|x)?(?![a-z0-9])", texte_normalise) is not None
