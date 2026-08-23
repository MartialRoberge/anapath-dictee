"""De quelle NATURE est une correction ?

LA QUESTION QUE "CORRIGE" NE REPOND PAS

Un praticien reecrit une phrase. Deux raisons possibles, sans rapport l'une avec
l'autre :

    le systeme s'est TROMPE          -> erreur, a corriger dans l'outil
    le praticien ecrit AUTREMENT     -> preference, a apprendre du laboratoire

Les compter ensemble donne un taux qui ne veut rien dire. Un outil dont 40 % des
propositions sont reformulees en style maison n'est pas un outil a 40 %
d'erreurs — mais un tableau qui ne separe pas les deux le dira, et personne ne
pourra le contredire.

DEUX MESURES INDEPENDANTES, ET C'EST VOULU

  DECLAREE  le praticien dit pourquoi il a corrige (style, precision, fond).
            C'est la seule source qui sait si le systeme avait TORT.
  CALCULEE  on compare le texte propose au texte retenu, ici, sans modele.
            C'est la seule source disponible sur les modifications que personne
            n'a declarees — celles faites au fil de l'eau dans le compte rendu,
            hors de toute proposition.

Leur DESACCORD est lui-meme une mesure : une correction declaree "style" dont le
calcul dit qu'un chiffre a change n'est pas une correction de style. Sans les
deux, on ne saurait pas que la declaration derive.

CE QUE LE CALCUL NE PEUT PAS DIRE, ET NE DIRA PAS

Le calcul voit qu'un contenu a change. Il ne peut pas savoir si le systeme avait
tort : "4,5 cm" corrige en "5,2 cm" peut etre une hallucination du systeme comme
une relecture de la lame par le praticien. Il rend donc `SUBSTANCE`, jamais
`erreur_fond` — cette imputation-la appartient au praticien seul.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Final

from etude.ancrage import decouper, jetons_discriminants

# --- Natures CALCULEES (a ne pas confondre avec les natures declarees) -----

IDENTIQUE: Final = "identique"
STYLE: Final = "style"
PRECISION: Final = "precision"
SUBSTANCE: Final = "substance"

NATURES_CALCULEES: Final[frozenset[str]] = frozenset(
    {IDENTIQUE, STYLE, PRECISION, SUBSTANCE}
)

#: Marqueurs de negation, sous leurs formes elidees et typographiques. Une
#: negation qui apparait ou disparait renverse le sens : c'est le changement le
#: plus grave qu'un diff puisse porter, et le plus facile a manquer a l'oeil.
_NEGATION: Final[re.Pattern[str]] = re.compile(
    r"\b(?:pas|non|sans|aucun[e]?|absence|ni|negatif[ve]*|indemne|exempt[e]?)\b"
    r"|\bn['’ ]",
    re.IGNORECASE,
)

_NOMBRE: Final[re.Pattern[str]] = re.compile(r"\d+(?:[.,]\d+)?")

#: Verbes et tournures de CONSTAT. Ils disent qu'on observe, jamais ce qu'on
#: observe : "la biopsie montre une lesion" et "lesion vue sur la biopsie"
#: affirment la meme chose. Les compter comme du contenu ferait passer toute
#: reformulation pour un changement de fond — c'est-a-dire exactement l'erreur
#: que ce module existe pour eviter.
#:
#: "presence" et "absence" n'y figurent pas : ceux-la portent la polarite.
_CONSTAT: Final[frozenset[str]] = frozenset({
    "montre", "montrent", "montrant",
    "observe", "observee", "observees", "observes", "observant",
    "note", "notee", "notees", "notes",
    "retrouve", "retrouvee", "retrouvees", "retrouves",
    "objective", "objectivee", "objectivees",
    "met", "mis", "mise", "evidence",
    "voit", "vue", "vues", "vu",
    "constate", "constatee", "decrit", "decrite",
    "existe", "trouve", "trouvee", "revele", "revelee",
    "examen", "analyse", "etude", "lecture",
})


def _contenu(texte: str) -> set[str]:
    """Les termes qui portent du CONTENU, hors tournures de constat."""
    return {jeton for jeton in jetons_discriminants(texte) if jeton not in _CONSTAT}


@dataclass(frozen=True)
class Ecart:
    """Ce qui a change entre le texte propose et le texte retenu.

    Les trois signaux restent SEPARES et lisibles : au depouillement, savoir
    QUE la nature est "substance" sert moins que savoir qu'un chiffre a change.
    """

    nature: str
    #: Les mesures ne sont plus les memes. Signal le plus dur du lot.
    chiffres_modifies: bool
    #: Une negation apparait ou disparait : le sens est renverse.
    negation_modifiee: bool
    #: Termes ajoutes et retires, hors mots vides.
    termes_ajoutes: tuple[str, ...]
    termes_retires: tuple[str, ...]
    #: Part de caracteres touches, pour trier les corrections par ampleur.
    ampleur: float


def _nombres(texte: str) -> list[str]:
    """Les nombres du texte, virgule et point ramenes a la meme forme."""
    return sorted(m.group(0).replace(".", ",") for m in _NOMBRE.finditer(texte))


def _negations(texte: str) -> int:
    return len(_NEGATION.findall(texte))


def _ampleur(propose: str, retenu: str) -> float:
    """Part de caracteres touches, de 0 (identique) a 1 (tout reecrit)."""
    if not propose and not retenu:
        return 0.0
    matcher = SequenceMatcher(None, propose, retenu, autojunk=False)
    touches = sum(
        max(i2 - i1, j2 - j1)
        for tag, i1, i2, j1, j2 in matcher.get_opcodes()
        if tag != "equal"
    )
    # Un remplacement compte au plus tout le texte : sans ce plafond,
    # l'ampleur depasse 1 et ne se compare plus d'une correction a l'autre.
    return round(min(1.0, touches / max(len(propose), len(retenu), 1)), 3)


def classer(propose: str, retenu: str) -> Ecart:
    """Classe une correction sans modele et sans avis clinique.

    L'ordre des tests est l'ordre de gravite : un chiffre ou une negation qui
    bougent tranchent seuls, meme si le reste du texte est identique. C'est
    volontaire — "4,5 cm" devenu "5,2 cm" est une correction de fond, pas une
    retouche, quelle que soit la part de caracteres touches.
    """
    chiffres = _nombres(propose) != _nombres(retenu)
    negation = _negations(propose) != _negations(retenu)

    avant = _contenu(propose)
    apres = _contenu(retenu)
    ajoutes = tuple(sorted(apres - avant))
    retires = tuple(sorted(avant - apres))

    ecart = _ampleur(propose, retenu)

    if propose == retenu:
        nature = IDENTIQUE
    elif chiffres or negation or retires:
        # Un terme retire est un contenu qui disparait : le systeme avait
        # affirme quelque chose que le praticien retire. C'est de la substance,
        # meme si rien d'autre ne bouge.
        nature = SUBSTANCE
    elif ajoutes:
        # Rien n'est retire, rien ne bouge sur les chiffres : le praticien
        # COMPLETE. Le systeme n'avait pas tort, il n'en savait pas assez.
        nature = PRECISION
    else:
        # Memes termes, memes chiffres, meme polarite : seuls l'ordre, la
        # ponctuation ou les mots de liaison ont change. Le fond tient.
        nature = STYLE

    return Ecart(
        nature=nature,
        chiffres_modifies=chiffres,
        negation_modifiee=negation,
        termes_ajoutes=ajoutes,
        termes_retires=retires,
        ampleur=ecart,
    )


def declaration_coherente(declaree: str | None, calculee: str) -> bool:
    """La nature declaree par le praticien tient-elle face au calcul ?

    Une correction declaree "style" alors qu'un chiffre a change n'est pas une
    correction de style, quoi qu'en dise le formulaire. Ce desaccord ne se
    corrige pas tout seul : il se COMPTE, parce qu'un taux de declarations
    incoherentes dit si l'on peut se fier aux declarations tout court.
    """
    if declaree is None:
        return True
    if declaree == "style":
        return calculee in (IDENTIQUE, STYLE)
    if declaree == "precision":
        return calculee in (IDENTIQUE, STYLE, PRECISION)
    # Une erreur de fond declaree est toujours recevable : le praticien peut
    # savoir que le systeme avait tort la ou le texte bouge a peine.
    return True


# --- Corrections faites hors proposition ----------------------------------


@dataclass(frozen=True)
class Retouche:
    """Un passage du compte rendu modifie sans passer par une proposition."""

    propose: str
    retenu: str
    ecart: Ecart


#: En dessous, un fragment ne porte pas de contenu jugeable : c'est de la
#: ponctuation ou un mot de liaison, et l'inonder de retouches masquerait les
#: vraies.
_MIN_JETONS_RETOUCHE: Final[int] = 3


def retouches_silencieuses(propose: str, retenu: str) -> list[Retouche]:
    """Les modifications du compte rendu qu'aucune decision n'explique.

    C'est le point aveugle de l'instrumentation : ce que le praticien reecrit
    directement dans le texte ne passe par aucun bouton, donc par aucune
    mesure. Or c'est precisement la que se cachent les erreurs du systeme qu'il
    a corrigees SANS qu'on lui ait demande de les juger — celles que le college
    avait affirmees, et sur lesquelles on ne l'a donc pas interroge.
    """
    matcher = SequenceMatcher(None, propose.split("\n"), retenu.split("\n"), autojunk=False)
    retouches: list[Retouche] = []

    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            continue
        avant = "\n".join(propose.split("\n")[i1:i2]).strip()
        apres = "\n".join(retenu.split("\n")[j1:j2]).strip()
        if not avant and not apres:
            continue
        if len(decouper(avant)) + len(decouper(apres)) < _MIN_JETONS_RETOUCHE:
            continue
        retouches.append(Retouche(propose=avant, retenu=apres, ecart=classer(avant, apres)))

    return retouches
