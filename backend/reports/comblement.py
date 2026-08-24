"""Combler les trous dont la reponse est DEJA dans la dictee.

LE DEFAUT QUE CE MODULE CORRIGE, mesure sur un cas reel.

Dictee : « ... TTF1+, PD-L1, 5%, analyse difficile, ALK negatif. »
Produit : « PD-L1 : [A COMPLETER: pourcentage de cellules tumorales positives] »

Le praticien a dit 5 %. On le lui redemande. C'est la pire chose que l'outil
puisse faire : il a parle pour ne pas avoir a taper, et on lui rend un
formulaire.

POURQUOI DETERMINISTE ET PAS DANS LE PROMPT. La regle est deja dans le prompt de
redaction, en toutes lettres et avec son exemple. Elle n'a pas suffi : sur une
dictee telegraphique — une etiquette, une virgule, une valeur — le modele ne
rattache pas la valeur a son etiquette. Une regle qui echoue sur le cas normal
n'est pas une regle, c'est un souhait. Ici, c'est verifie et ca ne depend
d'aucun modele.

CE N'EST PAS DE L'INTERPRETATION, c'est de la RESTITUTION. On ne comble que si
l'etiquette du trou figure dans la dictee, une seule fois, immediatement suivie
d'une valeur. Tout le reste reste un trou.
"""

from __future__ import annotations

import re
from typing import Final, NamedTuple

#: Le marqueur, tel que le moteur l'ecrit.
_MARQUEUR: Final[re.Pattern[str]] = re.compile(
    r"\[A COMPLETER\s*:\s*([^\]]+)\]", re.IGNORECASE
)

#: L'etiquette qui precede le marqueur : « PD-L1 : [A COMPLETER... ».
#: On remonte au plus 60 caracteres, jusqu'au debut de ligne ou a une puce.
_ETIQUETTE: Final[re.Pattern[str]] = re.compile(
    r"(?:^|\n)[\s\-*•]*\*{0,2}_{0,2}([^\n:*_|]{2,60}?)_{0,2}\*{0,2}\s*:\s*$"
)

#: Une valeur exploitable APRES l'etiquette dans la dictee : un nombre, un
#: pourcentage, ou un statut court. On n'attrape jamais une phrase : une phrase
#: n'est pas une valeur de champ, et l'inserer telle quelle serait du remplissage.
#: L'ordre des alternatives COMPTE : « 5% » doit etre lu comme un pourcentage,
#: pas comme le nombre 5. Une unite perdue dans un compte rendu signe est une
#: erreur clinique, pas une coquette.
_VALEUR: Final[re.Pattern[str]] = re.compile(
    r"^[\s:,;=–-]*("
    r"\d+(?:[.,]\d+)?\s*%"                   # 5 %, 12,5 %
    r"|\d+(?:[.,]\d+)?\s*(?:mm|cm|ml)\b"     # 18 mm
    r"|\d+(?:[.,]\d+)?(?![.,]?\d)(?!\s*[a-zA-Z])"  # 5, seul
    r"|(?:positif|negatif|négatif|positive|negative|négative"
    r"|present|présent|absent|absente)\b"
    r")",
    re.IGNORECASE,
)

#: Au-dela, l'etiquette et la valeur ne se touchent plus : « PD-L1 » en debut de
#: dictee et un « 5 % » trente mots plus loin ne se rattachent pas l'un a
#: l'autre. C'est exactement le faux ancrage qu'on a deja paye une fois.
_FENETRE: Final[int] = 24


class Comblement(NamedTuple):
    """Un trou comble, et de quoi le justifier au praticien."""

    champ: str
    valeur: str
    #: Le passage de la dictee d'ou vient la valeur, recopie.
    source: str


def _normaliser(texte: str) -> str:
    """Compare sans accents ni casse : « PD-L1 » doit retrouver « pd-l1 »."""
    sans_accent = (
        texte.replace("é", "e").replace("è", "e").replace("ê", "e")
        .replace("à", "a").replace("ç", "c").replace("ô", "o").replace("û", "u")
    )
    return sans_accent.casefold()


def _valeur_dans_la_dictee(etiquette: str, dictee: str) -> tuple[str, str] | None:
    """La valeur qui suit cette etiquette dans la dictee, si elle est unique.

    UNIQUE, et c'est essentiel : une etiquette qui apparait deux fois avec deux
    valeurs differentes ne permet pas de choisir, et choisir au hasard
    ecrirait un chiffre faux dans un compte rendu signe. On laisse le trou.
    """
    cible = _normaliser(etiquette.strip())
    if len(cible) < 3:
        return None

    foyer = _normaliser(dictee)
    positions = [
        trouve.start()
        for trouve in re.finditer(re.escape(cible), foyer)
    ]
    if len(positions) != 1:
        return None

    debut = positions[0] + len(cible)
    fenetre = dictee[debut : debut + _FENETRE]
    trouve = _VALEUR.match(fenetre)
    if trouve is None:
        return None

    valeur = " ".join(trouve.group(1).split())
    # Le passage recopie, pour que le praticien verifie lui-meme.
    source = " ".join(dictee[positions[0] : debut + trouve.end()].split())
    return valeur, source


def combler_depuis_la_dictee(cr: str, dictee: str) -> tuple[str, list[Comblement]]:
    """Remplace les trous dont la reponse figure dans la dictee.

    Rend le compte rendu corrige et la liste de ce qui a ete comble, pour que
    l'explicabilite puisse dire d'ou vient chaque valeur. Un comblement qu'on
    ne peut pas justifier serait indistinguable d'une invention.
    """
    if not cr or not dictee:
        return cr, []

    combles: list[Comblement] = []

    def _remplacer(trouve: re.Match[str]) -> str:
        champ = trouve.group(1).strip()
        avant = cr[: trouve.start()]
        etiquette = _ETIQUETTE.search(avant)
        if etiquette is None:
            return trouve.group(0)
        resultat = _valeur_dans_la_dictee(etiquette.group(1), dictee)
        if resultat is None:
            return trouve.group(0)
        valeur, source = resultat
        combles.append(Comblement(champ=champ, valeur=valeur, source=source))
        return valeur

    return _MARQUEUR.sub(_remplacer, cr), combles
