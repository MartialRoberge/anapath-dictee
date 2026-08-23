"""Ancrage d'un fragment de compte rendu dans le verbatim de la dictee.

Ce module repond a UNE question : quel passage de la dictee soutient ce
fragment de compte rendu ? Il retourne un empan, ou rien.

Retourner rien est un resultat, pas un echec. Ce que l'appelant en fait depend
de ce qu'il tient : un CODE sans appui n'est pas affichable, car le praticien ne
saurait pas sur quoi le juger ; une ASSERTION CLINIQUE sans appui est au
contraire la donnee la plus precieuse de l'etude — c'est une candidate
hallucination, et la supprimer effacerait la mesure centrale. Voir
extraction.py, qui tranche selon le type.

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

#: Prefixe partage a partir duquel deux formes sont tenues pour la meme chose.
#: Six : ganglionnaire correspond a ganglion, mais adenome ne correspond PAS a
#: adenocarcinome (prefixe commun "adeno", cinq caracteres).
_PREFIXE_MIN: Final[int] = 6

#: Longueur a partir de laquelle on tolere une substitution, pour rattraper une
#: erreur de transcription sans ouvrir la porte aux mots courts homographes.
_DISTANCE_MIN_LONGUEUR: Final[int] = 8

#: Un terme de cette longueur suffit SEUL a ancrer un fragment.
#:
#: Les fragments courts ont un taux grossier : avec deux jetons discriminants,
#: le taux ne peut valoir que 0, 0,5 ou 1, et le seuil de 0,55 rejette 1 sur 2.
#: Mesure sur cas reels : "Il n'est pas observe de mucosecretion" etait declare
#: non dicte alors que la dictee porte "pas de mycosecretion" — un mot pour
#: l'autre. En francais medical, un terme de dix caracteres est un terme
#: technique, pas du remplissage : le retrouver est une preuve a lui seul.
_LONGUEUR_ANCRE_FORTE: Final[int] = 10

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
class Correspondance:
    """Ce que le fragment partage avec le verbatim.

    Les trois signaux restent SEPARES et aucun n'en corrige un autre : le taux
    est la trace du calcul, consignee telle quelle pour le depouillement. Le
    gonfler pour faire passer un seuil rendrait la donnee inexploitable.
    """

    #: Formes du verbatim visees, pour la recherche de fenetre.
    cibles: set[str]
    #: Part des jetons attendus retrouves. Trace du calcul, jamais ajustee.
    recouvrement: float
    #: Nombre de jetons attendus retrouves.
    couverts: int
    #: Un terme technique long a ete retrouve : preuve suffisante a lui seul.
    ancre_forte: bool


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


def _prefixe_commun(gauche: str, droit: str) -> int:
    """Longueur du plus long prefixe partage par les deux formes."""
    taille = 0
    for a, b in zip(gauche, droit):
        if a != b:
            break
        taille += 1
    return taille


def _distance_1(gauche: str, droit: str) -> bool:
    """Les deux formes different-elles d'au plus une substitution ?

    Sert a rattraper les erreurs de transcription : la dictee entendue
    "mycosecretion" pour "mucosecretion" ne partage aucun prefixe utile, et sans
    cette tolerance l'assertion correspondante serait declaree non dictee — on
    compterait une erreur de STT comme une hallucination du moteur, alors que
    l'etude tient justement a distinguer les deux.
    """
    if len(gauche) != len(droit):
        return False
    ecarts = sum(1 for a, b in zip(gauche, droit) if a != b)
    return ecarts == 1


def _correspond(attendu: str, forme: str) -> bool:
    """Deux formes designent-elles la meme chose, pour l'ancrage ?

    L'egalite stricte ne suffit pas : le praticien dicte en style telegraphique
    ("lobe inferieur droit avec curage") et le compte rendu redige en prose
    ("piece de lobectomie inferieure droite"). Mesure sur cas reels : avec la
    seule egalite, les constatations NEGATIVES etaient toutes ecartees, alors
    que ce sont les affirmations les plus dangereuses a laisser passer.

    Le seuil de six caracteres n'est pas arbitraire : il fait correspondre
    ganglionnaire a ganglion et infiltration a infiltre, mais PAS adenome a
    adenocarcinome, qui ne partagent que "adeno". Confondre ces deux-la serait
    une faute clinique.
    """
    if attendu == forme:
        return True
    if len(attendu) >= _PREFIXE_MIN and len(forme) >= _PREFIXE_MIN:
        if _prefixe_commun(attendu, forme) >= _PREFIXE_MIN:
            return True
    return len(attendu) >= _DISTANCE_MIN_LONGUEUR and _distance_1(attendu, forme)


def _cibles_presentes(
    fragment: str, formes_verbatim: frozenset[str]
) -> Correspondance:
    """Ancres du fragment dans le verbatim : formes visees, taux, et compte.

    Le compte porte sur les jetons ATTENDUS couverts, pas sur les formes du
    verbatim : un seul terme du fragment peut correspondre a plusieurs formes
    dictees, et les additionner gonflerait artificiellement la preuve.

    Le denominateur exclut les nombres (voir `_est_discriminant`) : les compter
    penaliserait toute reformulation chiffree alors qu'ils n'ancrent rien.
    """
    attendus = set(jetons_discriminants(fragment))
    if not attendus:
        return Correspondance(set(), 0.0, 0, False)

    # On retourne les formes DU VERBATIM, pas celles du fragment : ce sont elles
    # que la recherche de fenetre compare ensuite aux jetons de la dictee.
    cibles: set[str] = set()
    couverts = 0
    ancre_forte = False
    for attendu in attendus:
        correspondantes = {f for f in formes_verbatim if _correspond(attendu, f)}
        if correspondantes:
            couverts += 1
            cibles |= correspondantes
            if len(attendu) >= _LONGUEUR_ANCRE_FORTE:
                ancre_forte = True

    # Les nombres n'entrent NI au numerateur NI au denominateur. Mesure sur cas
    # reels : "PD-L1 : expression tumorale evaluee a 5 %" s'ancrait sur "5 mm,
    # deux plans de coupe" — le 5 d'un pourcentage accroche par le 5 d'une
    # mesure. Le praticien relisait une taille pour juger un marqueur. Un chiffre
    # nu se retrouve partout : ce n'est pas une ancre, c'est une coincidence.
    return Correspondance(
        cibles=cibles,
        recouvrement=couverts / len(attendus),
        couverts=couverts,
        ancre_forte=ancre_forte,
    )


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
    meilleure = (0, -1, 0, len(jetons) + 1)  # (debut, fin, couverture, longueur)
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
        candidat = _resserrer(jetons, cibles, gauche, droite)
        if candidat is None:
            continue
        longueur = candidat[1] - candidat[0]
        # A couverture egale on prend la fenetre la PLUS COURTE, pas la premiere
        # rencontree. Sans ce departage, une conclusion diagnostique s'ancrait
        # sur la macroscopie : elle est dictee en premier, donc la premiere
        # fenetre atteignant la couverture maximale y tombe presque toujours.
        if (len(compte), -longueur) > (meilleure[2], -meilleure[3]):
            meilleure = (candidat[0], candidat[1], len(compte), longueur)

    if meilleure[2] == 0:
        return None
    return meilleure[0], meilleure[1]


def _resserrer(
    jetons: list[Jeton], cibles: set[str], debut: int, fin: int
) -> tuple[int, int] | None:
    """Rogne les bords jusqu'a ce qu'ils soient des cibles.

    Un empan qui commence ou finit sur un mot quelconque designe plus large que
    necessaire. Retourne None si la fenetre ne contient aucune cible.
    """
    while debut <= fin and jetons[debut].forme not in cibles:
        debut += 1
    if debut > fin:
        return None
    while fin > debut and jetons[fin].forme not in cibles:
        fin -= 1
    return debut, fin


def _preuve_suffisante(trouve: Correspondance, seuil: float) -> bool:
    """Le fragment porte-t-il assez de preuves pour etre ancre ?

    Trois voies, et une seule suffit :
    - un TAUX eleve : le fragment reformule un passage ;
    - assez d'ANCRES en valeur absolue : une inference qui reprend la
      topographie et plusieurs termes du cas ;
    - une ANCRE FORTE : un terme technique long, qui n'apparait pas par hasard.
    """
    if trouve.ancre_forte:
        return True
    return trouve.recouvrement >= seuil or trouve.couverts >= MIN_ANCRES_ABSOLU


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
    trouve = _cibles_presentes(fragment, formes)
    if not _preuve_suffisante(trouve, seuil):
        return None

    fenetre = _meilleure_fenetre(jetons, trouve.cibles)
    if fenetre is None:
        return None

    debut_jeton, fin_jeton = fenetre
    debut = jetons[debut_jeton].debut
    fin = jetons[fin_jeton].fin
    return Empan(
        debut=debut,
        fin=fin,
        extrait=verbatim[debut:fin],
        recouvrement=round(trouve.recouvrement, 3),
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
    if _cibles_presentes(fragment, formes).recouvrement < seuil:
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
