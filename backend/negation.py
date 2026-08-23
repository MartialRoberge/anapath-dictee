"""Negation — SOURCE UNIQUE. Empeche de coder une lesion qui est niee.

adicap.py et snomed.py cherchent des mots-cles de lesion dans le texte. Ce
module blanchit ce qui est nie AVANT cette recherche, pour qu'une lesion
absente ne recoive pas de code.

POURQUOI ON NE MASQUE PLUS DES PORTEES

La version precedente masquait du marqueur jusqu'a un separateur. Deux
reecritures successives ont echoue sur le meme mur, et le mur est de langue,
pas de code : LA PORTEE D'UNE NEGATION FRANCAISE NE SE DELIMITE PAS PAR UNE
LISTE DE MOTS.

    "pas d'atypie cytonucleaire associee a une hyperplasie glandulaire"
    "ni granulome ni necrose, au contraire une hyperplasie lymphoide"

Dans les deux, la lesion affirmee suit la negation dans la meme proposition. En
masquant jusqu'au point, on l'effacait — et une lesion reelle qui disparait du
codage est PIRE que le defaut d'origine : elle ne laisse aucune trace.

CE QU'ON FAIT A LA PLACE

On ne masque plus un intervalle, on masque DES TERMES. Pour chaque declencheur,
on regarde en avant sur une fenetre bornee et on blanchit les mots porteurs de
sens rencontres, en s'arretant a la premiere rupture. C'est la methode NegEx
(Chapman et al., 2001), qui est le standard du domaine pour cette raison
precise.

La propriete qui compte : une erreur reste LOCALE. Au pire un terme de trop est
masque, jamais une phrase entiere. Un mot situe au-dela de la fenetre, ou apres
une rupture, est hors d'atteinte par construction.

DEUX SENS DE LECTURE

CE QUI ENTRE ICI EST UN COMPTE RENDU, PAS UNE DICTEE

adicap.py et snomed.py codent le RAPPORT GENERE, pas le verbatim : de la prose
ponctuee. La ponctuation est donc un signal disponible, et le cas de la dictee
sans ponctuation ne se presente pas sur ce chemin. Le rappeler evite de
recalibrer les fenetres pour un scenario qui n'arrive jamais ici — ce qui a
deja fait perdre du temps.

En avant pour la prose : "pas de signe de malignite".
En arriere pour les listes synoptiques, ou la negation suit ce qu'elle nie :
"Emboles vasculaires : non". Le masque arriere est plus court, parce qu'une
etiquette de checklist l'est.
"""

from __future__ import annotations

import re
from typing import Final

from text_utils import normaliser

# --- Fenetres --------------------------------------------------------------

#: Mots PORTEURS examines apres un declencheur — les mots grammaticaux ne
#: comptent pas. "pas de signe de malignite" en consomme deux, pas quatre.
#:
#: Quatre couvre les enumerations courantes du francais medical ("pas de
#: dysplasie, d'atypie ni de mitose") et reste tres en deca d'une proposition.
#: Au-dela, la mesure sur les 653 textes reels ne gagne plus rien et le risque
#: d'attraper une affirmation voisine augmente.
FENETRE_AVANT: Final[int] = 4

#: Mots examines avant une negation post-posee. Une etiquette de checklist tient
#: en quelques mots ("Emboles vasculaires lymphatiques : non") ; au-dela on
#: remonterait dans la phrase precedente.
FENETRE_ARRIERE: Final[int] = 3


def _formes(*variantes: str) -> tuple[str, ...]:
    """Decline une tournure elidee sous ses trois ecritures reelles.

    "absence d'" s'ecrit avec une apostrophe droite, une apostrophe
    typographique, ou une espace quand la dictee vocale ne transcrit pas
    l'elision. N'en traiter qu'une laisse passer les deux autres — c'etait le
    defaut d'origine, et il codait un adenocarcinome sur une piece en reponse
    complete.
    """
    sorties: list[str] = []
    for variante in variantes:
        if "'" in variante:
            base = variante.replace("'", "")
            sorties += [variante, variante.replace("'", "’"), base + " "]
        else:
            sorties.append(variante)
    return tuple(sorties)


#: Declencheurs de negation, en texte NORMALISE. Publics : specimen_type.py
#: s'en sert pour savoir si un terme precis est precede d'une negation, sans
#: avoir a masquer tout le texte.
#: En texte NORMALISE (minuscule, sans accents).
#: Chacun est cherche a une frontiere de mot : sans cela "ni de" matchait dans
#: "aciNI DE la glande" et "libre de" dans "caLIBRE DEs glandes", effacant des
#: descriptions reelles.
DECLENCHEURS: Final[tuple[str, ...]] = (
    *_formes("absence d'", "absence de"),
    *_formes("pas d'", "pas de", "pas la", "pas le", "pas un", "pas une"),
    *_formes("plus d'", "plus de"),
    *_formes("aucun", "aucune"),
    *_formes("ni d'", "ni de", "ni "),
    *_formes("sans "),
    *_formes("indemne d'", "indemne de", "indemnes d'", "indemnes de"),
    *_formes("exempt d'", "exempt de", "exempte d'", "exempte de"),
    *_formes("depourvu d'", "depourvu de", "depourvue d'", "depourvue de"),
    *_formes("negatif pour", "negative pour"),
    *_formes("non retrouve", "non retrouvee", "non identifie", "non identifiee"),
    *_formes("non observe", "non observee", "non vu", "non vue"),
    *_formes("exclut", "elimine"),
    *_formes("jamais", "nullement", "en aucun cas"),
    *_formes("rien en faveur d'", "rien en faveur de"),
    *_formes("en evidence d'", "en evidence de"),
)

#: "sans" n'introduit pas toujours une negation : dans "sans doute", il renforce
#: une affirmation. Masquer la suite y effacerait le diagnostic — c'est arrive.
_FAUX_DECLENCHEURS: Final[tuple[str, ...]] = (
    "sans doute", "sans nul doute", "sans aucun doute",
    "sans conteste", "sans equivoque", "sans ambiguite",
)

#: Negations post-posees des comptes rendus synoptiques.
_DECLENCHEURS_ARRIERE: Final[tuple[str, ...]] = (
    ": non", ": absent", ": absente", ": absents", ": absentes",
    ": nul", ": nulle", ": negatif", ": negative",
    "sont absents", "sont absentes", "est absent", "est absente",
    "non identifie", "non identifiee", "non identifies", "non identifiees",
)

#: RUPTURES — ce qui rend la main a l'affirmation.
#:
#: C'est la piece qui manquait. "pas d'atypie ASSOCIEE A une hyperplasie" :
#: l'hyperplasie n'est pas niee, elle est affirmee dans la meme proposition.
#: Sans ces ruptures, aucune fenetre, si courte soit-elle, ne la protege.
_RUPTURES: Final[tuple[str, ...]] = (
    "mais", "cependant", "toutefois", "neanmoins", "revanche", "contraire",
    "associe", "associee", "associes", "associees",
    "accompagne", "accompagnee", "accompagnes", "accompagnees",
    "avec", "presence", "presente", "presentant", "surmonte", "surmontee",
    "hormis", "excepte", "exception", "sauf", "alors", "tandis", "sinon",
    "remplace", "remplacee", "au", "profit",
)

_SEPARATEURS: Final[tuple[str, ...]] = (".", ";", "\n", ":", "!", "?")

#: La virgule est ambigue, et c'est le dernier piege du francais medical :
#:
#:   "pas de dysplasie, d'atypie ni de mitose"      -> l'enumeration CONTINUE
#:   "aucun ganglion envahi, adenocarcinome de..."  -> une affirmation COMMENCE
#:
#: Ce qui les separe est le mot d'apres : une enumeration reprend par une
#: preposition ou une conjonction, une affirmation par un substantif. On coupe
#: donc sur la virgule, sauf si la suite enchaine.
_ENCHAINEMENTS: Final[frozenset[str]] = frozenset({
    "de", "d", "des", "du", "ni", "ou", "et", "a", "au", "aux", "en",
})

_MOT: Final[re.Pattern[str]] = re.compile(r"[^\W\d_]+")

#: Mots trop courts ou trop communs pour porter une lesion. Les blanchir ne
#: servirait a rien et abimerait la lisibilite du texte masque.
_INSIGNIFIANTS: Final[frozenset[str]] = frozenset({
    "de", "du", "des", "la", "le", "les", "un", "une", "d", "l", "et", "ou",
    "en", "a", "au", "aux", "ce", "cet", "cette", "ces", "son", "sa", "ses",
    "est", "sont", "il", "elle", "on", "y", "se", "ne", "n", "qui", "que",
})


def _est_faux_declencheur(texte: str, position: int) -> bool:
    """Le declencheur trouve fait-il partie d'une tournure d'affirmation ?"""
    return any(
        texte.startswith(faux, position) for faux in _FAUX_DECLENCHEURS
    )


def _debut_de_mot(texte: str, position: int) -> bool:
    """Le declencheur commence-t-il bien un mot ?"""
    return position == 0 or not texte[position - 1].isalnum()


def _mots_apres(texte: str, depart: int, fenetre: int) -> list[re.Match[str]]:
    """Les mots qui suivent, jusqu'a une rupture ou un separateur."""
    retenus: list[re.Match[str]] = []
    curseur = depart
    for correspondance in _MOT.finditer(texte, depart):
        entre_deux = texte[curseur:correspondance.start()]
        if any(sep in entre_deux for sep in _SEPARATEURS):
            break
        forme = correspondance.group(0)
        if "," in entre_deux and forme not in _ENCHAINEMENTS:
            break
        if forme in _RUPTURES:
            break
        curseur = correspondance.end()
        if forme in _INSIGNIFIANTS:
            # Un mot grammatical ne consomme pas la fenetre : sinon "pas de
            # signe de malignite" epuiserait quatre places pour deux termes.
            continue
        retenus.append(correspondance)
        if len(retenus) >= fenetre:
            break
    return retenus


def _mots_avant(texte: str, fin: int, fenetre: int) -> list[re.Match[str]]:
    """Les mots qui precedent, jusqu'a une rupture ou un separateur."""
    candidats = [m for m in _MOT.finditer(texte, 0, fin)]
    retenus: list[re.Match[str]] = []
    borne = fin
    for correspondance in reversed(candidats):
        entre_deux = texte[correspondance.end():borne]
        if any(sep in entre_deux for sep in _SEPARATEURS):
            break
        forme = correspondance.group(0)
        if forme in _RUPTURES:
            break
        borne = correspondance.start()
        if forme in _INSIGNIFIANTS:
            continue
        retenus.append(correspondance)
        if len(retenus) >= fenetre:
            break
    return retenus


def _a_blanchir(texte: str) -> list[tuple[int, int]]:
    """Les intervalles de mots nies, dans les deux sens de lecture."""
    intervalles: list[tuple[int, int]] = []

    for declencheur in DECLENCHEURS:
        depart = texte.find(declencheur)
        while depart != -1:
            if _debut_de_mot(texte, depart) and not _est_faux_declencheur(texte, depart):
                fin_declencheur = depart + len(declencheur)
                intervalles.append((depart, fin_declencheur))
                for mot in _mots_apres(texte, fin_declencheur, FENETRE_AVANT):
                    intervalles.append((mot.start(), mot.end()))
            depart = texte.find(declencheur, depart + 1)

    for declencheur in _DECLENCHEURS_ARRIERE:
        depart = texte.find(declencheur)
        while depart != -1:
            for mot in _mots_avant(texte, depart, FENETRE_ARRIERE):
                intervalles.append((mot.start(), mot.end()))
            depart = texte.find(declencheur, depart + 1)

    return intervalles


def mask_negations(texte: str) -> str:
    """Blanchit les TERMES nies, en conservant les positions du reste.

    "adenocarcinome, absence de metastase." garde "adenocarcinome" et perd
    "metastase" : un mot-cle cherche ensuite ne peut plus matcher dans ce qui
    est nie.

    Le texte garde exactement sa longueur : les appelants comparent parfois des
    positions entre le texte d'origine et le texte masque.
    """
    if not texte:
        return texte
    caracteres = list(texte)
    for debut, fin in _a_blanchir(texte):
        for index in range(debut, min(fin, len(caracteres))):
            caracteres[index] = " "
    return "".join(caracteres)


def est_nie(texte: str, terme: str) -> bool:
    """Le terme apparait-il UNIQUEMENT sous une negation ?

    Utile a qui cherche un mot-cle precis plutot qu'a masquer tout un texte :
    la reponse est vraie seulement si aucune occurrence n'echappe au masque.
    """
    normalise = normaliser(texte)
    cible = normaliser(terme)
    if cible not in normalise:
        return False
    return cible not in mask_negations(normalise)
