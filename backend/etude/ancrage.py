"""Ancrage d'un fragment de compte rendu dans le verbatim de la dictee.

REGLE FONDATRICE DE L'ETUDE : pas d'empan, pas de proposition.

Une proposition qu'on ne sait pas rattacher a un passage precis de la dictee
n'est pas affichable : le praticien devrait relire tout son verbatim pour la
juger, il validerait par lassitude, et le taux mesure ne vaudrait rien. Une
proposition non ancree est donc rejetee AVANT affichage, pas signalee apres.

L'empan est calcule ICI, cote serveur, par recouvrement de jetons. On ne
demande JAMAIS des offsets a un modele de langage : il les invente, et un
surlignage decale a la mauvaise phrase est pire que pas de surlignage — il
fait valider un mot pour un autre.

Le calcul est deterministe et reproductible : deux executions sur les memes
entrees donnent le meme empan, ce qui est la condition pour publier.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Final

from text_utils import normaliser

# --- Parametres du recouvrement -------------------------------------------

#: Part des jetons discriminants du fragment qui doit se retrouver dans le
#: verbatim pour que l'ancrage soit accepte. En dessous, on considere que le
#: fragment parle d'autre chose et l'on refuse plutot que de surligner au hasard.
SEUIL_RECOUVREMENT: Final[float] = 0.55

#: Un empan qui s'etale sur tout le verbatim ne designe rien. On borne la
#: fenetre de recherche : la dictee est plus verbeuse que le compte rendu, mais
#: pas au point de diluer une assertion sur des centaines de mots.
FENETRE_MAX_JETONS: Final[int] = 60

#: En dessous de ce nombre de jetons discriminants, un fragment ne porte pas
#: assez d'information pour etre ancre sans ambiguite ("elle est presente").
MIN_JETONS_DISCRIMINANTS: Final[int] = 2

#: Nombre d'ancres retrouvees qui suffit A LUI SEUL, quel que soit le taux.
#:
#: Sans ce second critere, le taux seul rejetterait justement les propositions
#: qui comptent le plus. Une conclusion diagnostique est une INFERENCE : elle
#: introduit des mots que la dictee ne contient pas ("adenome tubuleux en
#: dysplasie de bas grade"), donc son taux de recouvrement est structurellement
#: bas alors qu'elle porte bien sur cette dictee — elle en reprend la
#: topographie et plusieurs termes. Le taux mesure la reformulation ; le compte
#: absolu mesure l'appartenance au cas. Une hallucination n'a ni l'un ni l'autre.
#:
#: A retenir : l'empan dit OU REGARDER, il ne prejuge pas de la justesse. Une
#: proposition fausse mais sur le sujet DOIT etre affichee et ancree — c'est
#: precisement en la rejetant que le praticien produit la mesure.
MIN_ANCRES_ABSOLU: Final[int] = 3

#: Le motif tourne sur le texte D'ORIGINE, accents compris : normaliser d'abord
#: decalerait les offsets, car "oe" remplace "œ" et gagne un caractere. Un empan
#: decale surligne un mot pour un autre — c'est pire que pas d'empan du tout.
_MOT: Final[re.Pattern[str]] = re.compile(r"[0-9]+(?:[.,][0-9]+)?|[^\W\d_]+")

_NOMBRE: Final[re.Pattern[str]] = re.compile(r"^[0-9]+(?:[.,][0-9]+)?$")

#: Mots vides : presents partout, ils n'ancrent rien et gonflent artificiellement
#: le recouvrement. Les retirer rend le seuil interpretable.
_MOTS_VIDES: Final[frozenset[str]] = frozenset({
    "a", "au", "aux", "avec", "ce", "ces", "cet", "cette", "dans", "de", "des",
    "du", "elle", "elles", "en", "est", "et", "eu", "il", "ils", "je", "la",
    "le", "les", "leur", "lui", "ma", "mais", "me", "meme", "mes", "moi", "mon",
    "ne", "nos", "notre", "nous", "on", "ou", "par", "pas", "peu", "plus",
    "pour", "qu", "que", "qui", "sa", "sans", "se", "ses", "son", "sont", "sur",
    "ta", "te", "tes", "toi", "ton", "tres", "tu", "un", "une", "vos", "votre",
    "vous", "y", "etre", "avoir", "cela", "donc", "alors", "ici", "la",
    "aussi", "comme", "entre", "sous", "vers", "chez", "apres", "avant",
})


@dataclass(frozen=True)
class Jeton:
    """Un mot du verbatim, avec sa position exacte dans le texte d'origine."""

    forme: str
    debut: int
    fin: int


@dataclass(frozen=True)
class Empan:
    """Le passage du verbatim qui porte une proposition.

    `recouvrement` est la trace du calcul : il permet, au depouillement, de
    distinguer un ancrage franc d'un ancrage limite.
    """

    debut: int
    fin: int
    extrait: str
    recouvrement: float


def decouper(texte: str) -> list[Jeton]:
    """Decoupe le texte en jetons normalises, en gardant leurs offsets.

    Les offsets pointent vers le texte d'ORIGINE : c'est lui que le frontend
    surligne. La normalisation s'applique jeton par jeton, APRES le reperage
    des positions, pour que les deux ne puissent pas diverger.
    """
    return [
        Jeton(forme=normaliser(m.group(0)), debut=m.start(), fin=m.end())
        for m in _MOT.finditer(texte)
    ]


def _est_discriminant(forme: str) -> bool:
    """Le jeton porte-t-il assez d'information pour servir d'ancre ?"""
    if _NOMBRE.match(forme):
        # Les chiffres comptent quand ils correspondent, mais ne sont pas exiges :
        # la dictee dit "quatre virgule cinq", le compte rendu ecrit "4,5".
        return False
    return len(forme) > 2 and forme not in _MOTS_VIDES


def jetons_discriminants(texte: str) -> list[str]:
    """Les formes du texte qui peuvent servir d'ancre, dans l'ordre."""
    return [j.forme for j in decouper(texte) if _est_discriminant(j.forme)]


def _cibles_presentes(
    fragment: str, formes_verbatim: frozenset[str]
) -> tuple[set[str], float]:
    """Jetons du fragment retrouves dans le verbatim, et taux de recouvrement.

    Le denominateur exclut les nombres (voir `_est_discriminant`) : les compter
    penaliserait toute reformulation chiffree alors qu'ils n'ancrent rien.
    """
    attendus = set(jetons_discriminants(fragment))
    if not attendus:
        return set(), 0.0
    trouves = {f for f in attendus if f in formes_verbatim}
    # Un nombre retrouve tel quel renforce l'ancrage sans jamais le degrader.
    bonus = {
        j.forme
        for j in decouper(fragment)
        if _NOMBRE.match(j.forme) and j.forme in formes_verbatim
    }
    return trouves | bonus, len(trouves) / len(attendus)


def _meilleure_fenetre(
    jetons: list[Jeton], cibles: set[str]
) -> tuple[int, int] | None:
    """Fenetre de jetons couvrant le plus de cibles distinctes, la plus courte.

    Deux temps : on balaie une fois pour trouver la meilleure couverture
    atteignable dans une fenetre bornee, puis on resserre les bords tant que la
    couverture ne baisse pas. Le resserrage est ce qui evite de surligner un
    paragraphe entier pour trois mots.
    """
    if not cibles or not jetons:
        return None

    compte: dict[str, int] = {}
    meilleure = (0, -1, 0)  # (debut, fin, couverture)
    gauche = 0

    for droite, jeton in enumerate(jetons):
        if jeton.forme in cibles:
            compte[jeton.forme] = compte.get(jeton.forme, 0) + 1
        while droite - gauche + 1 > FENETRE_MAX_JETONS:
            sortant = jetons[gauche].forme
            if sortant in compte:
                compte[sortant] -= 1
                if compte[sortant] == 0:
                    del compte[sortant]
            gauche += 1
        if len(compte) > meilleure[2]:
            meilleure = (gauche, droite, len(compte))

    debut, fin, couverture = meilleure
    if couverture == 0:
        return None
    return _resserrer(jetons, cibles, debut, fin, couverture)


def _resserrer(
    jetons: list[Jeton], cibles: set[str], debut: int, fin: int, couverture: int
) -> tuple[int, int]:
    """Rogne les bords de la fenetre tant que la couverture est preservee."""
    while debut < fin and jetons[debut].forme not in cibles:
        debut += 1
    while fin > debut and jetons[fin].forme not in cibles:
        fin -= 1
    # Les bords sont maintenant des cibles ; on ne peut resserrer davantage
    # qu'en perdant une occurrence, donc en risquant de perdre la couverture.
    del couverture
    return debut, fin


def ancrer(
    fragment: str, verbatim: str, seuil: float = SEUIL_RECOUVREMENT
) -> Empan | None:
    """Localise le fragment dans le verbatim, ou refuse de le localiser.

    Retourne None des que l'ancrage n'est pas franc : c'est le comportement
    attendu. Une proposition sans empan ne doit pas etre affichee.
    """
    jetons = decouper(verbatim)
    if not jetons:
        return None

    attendus = jetons_discriminants(fragment)
    if len(set(attendus)) < MIN_JETONS_DISCRIMINANTS:
        return None

    formes = frozenset(j.forme for j in jetons)
    cibles, recouvrement = _cibles_presentes(fragment, formes)
    if recouvrement < seuil and len(cibles) < MIN_ANCRES_ABSOLU:
        return None

    fenetre = _meilleure_fenetre(jetons, cibles)
    if fenetre is None:
        return None

    debut_jeton, fin_jeton = fenetre
    debut = jetons[debut_jeton].debut
    fin = jetons[fin_jeton].fin
    return Empan(
        debut=debut,
        fin=fin,
        extrait=verbatim[debut:fin],
        recouvrement=round(recouvrement, 3),
    )


def est_copie_litterale(
    fragment: str, verbatim: str, seuil: float = 0.95
) -> bool:
    """Le fragment est-il une reprise mot pour mot de la dictee ?

    Cahier de recueil : ce qui est une copie litterale du verbatim n'est pas une
    proposition, c'est une transcription. Seule l'inference se valide. Sans ce
    filtre, on gonflerait le taux d'acceptation avec des evidences.
    """
    attendus = jetons_discriminants(fragment)
    if not attendus:
        return True
    formes = frozenset(j.forme for j in decouper(verbatim))
    _, recouvrement = _cibles_presentes(fragment, formes)
    if recouvrement < seuil:
        return False
    # Recouvrement quasi total ET meme ordre : c'est une reprise, pas une
    # reformulation. L'ordre distingue "adenocarcinome du colon" repete tel quel
    # d'une conclusion qui reassemble des mots dictes a des endroits differents.
    return _apparait_en_ordre(attendus, [j.forme for j in decouper(verbatim)])


def _apparait_en_ordre(attendus: list[str], verbatim: list[str]) -> bool:
    """Les formes attendues apparaissent-elles dans cet ordre dans le verbatim ?"""
    position = 0
    for forme in attendus:
        while position < len(verbatim) and verbatim[position] != forme:
            position += 1
        if position == len(verbatim):
            return False
        position += 1
    return True
