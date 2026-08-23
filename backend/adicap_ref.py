"""Lecture du thesaurus ADICAP officiel precalcule (data/adicap_ref.json).

Le fichier est produit par scripts/build_adicap_index.py a partir du classeur
ADICAP_2024.xlsx : ici on ne fait que le charger une fois, le mettre en cache et
l'interroger. Aucune dependance a openpyxl, aucun XLSX ouvert au runtime — le
deploiement Render n'envoie que backend/, d'ou un chemin resolu par rapport au
MODULE et jamais par rapport au repertoire courant.

Deux regles du referentiel se retrouvent dans cette API :
- l'identifiant d'un concept est son URI, jamais son code : le classeur compte
  9683 concepts pour 9394 codes distincts, et meme (dictionnaire, code) se
  repete. Toutes les recherches passent donc par l'URI ;
- 201 concepts portent une date de fin de validite. Ils restent consultables par
  `concept()` pour afficher un compte rendu ancien, mais sont exclus par defaut
  de `enfants()`, `lister_dictionnaire()` et `chercher()`, qui alimentent les
  propositions faites au praticien.

Corollaire de la premiere regle, et piege principal de ce module : le SUFFIXE
d'URI accepte en raccourci n'est PAS le code. Le concept D1H a pour suffixe
"D1H" et pour code "H". Les deux coincident pour 9161 concepts, ce qui donne
l'illusion qu'un code est une reference valide ; pour 453 autres le code ne
designe rien et l'echec est franc ; mais pour 69 concepts le code se trouve
etre le suffixe d'un AUTRE concept, et la reponse serait alors fausse sans le
moindre signal. Le cas le plus net : le code "EZ" appartient a D5EZ (TUMEUR
EPIDERMOIDE, une lesion) alors que le suffixe "EZ" designe SYSTEME ENDOCRINE
(un organe). Ces 69 references sont donc REFUSEES, voir `_uri_complete`.

Les libelles officiels sont en majuscules et presque toujours sans accents : les
comparer a du texte dicte impose de passer par text_utils, source unique de
normalisation du depot. Le libelle normalise n'est pas stocke dans le JSON, il
est recalcule au chargement pour qu'il n'existe qu'une seule normalisation.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from text_utils import normaliser

_CHEMIN_INDEX: Path = Path(__file__).resolve().parent / "data" / "adicap_ref.json"

# Doit correspondre a `colonnes` dans le JSON : un index reconstruit avec un
# autre schema doit echouer bruyamment plutot que decaler les champs.
_COLONNES_ATTENDUES: tuple[str, ...] = (
    "uri",
    "code",
    "uri_parent",
    "dictionnaire",
    "libelle",
    "fin_validite",
    "code_anatomie",
)

_LIMITE_DEFAUT: int = 20


@dataclass(frozen=True, slots=True)
class Concept:
    """Un concept du thesaurus, identifie par son URI."""

    uri: str
    code: str
    uri_parent: str
    dictionnaire: str
    libelle: str
    libelle_normalise: str
    fin_validite: str
    code_anatomie: str
    libelle_anatomie: str

    @property
    def obsolete(self) -> bool:
        """Vrai si le concept porte une date de fin : ne plus le proposer."""
        return bool(self.fin_validite)


@dataclass(frozen=True, slots=True)
class IndexAdicap:
    """Le thesaurus charge en memoire, pre-indexe pour les acces courants."""

    version: str
    base_uri: str
    par_uri: dict[str, Concept]
    enfants: dict[str, tuple[Concept, ...]]
    par_dictionnaire: dict[str, tuple[Concept, ...]]
    # Un code designe 0, 1 ou plusieurs concepts : le groupe sert a detecter
    # qu'une reference courte est lisible a la fois comme suffixe et comme code.
    par_code: dict[str, tuple[Concept, ...]]


def _concept(ligne: list[str], base_uri: str, anatomies: dict[str, str]) -> Concept:
    """Reconstruit un Concept depuis une ligne positionnelle du JSON."""
    uri, code, uri_parent, dictionnaire, libelle, fin, anatomie = ligne
    return Concept(
        uri=base_uri + uri,
        code=code,
        uri_parent=base_uri + uri_parent if uri_parent else "",
        dictionnaire=dictionnaire,
        libelle=libelle,
        libelle_normalise=normaliser(libelle),
        fin_validite=fin,
        code_anatomie=anatomie,
        libelle_anatomie=anatomies.get(anatomie, ""),
    )


def _grouper(
    concepts: list[Concept], cle: Callable[[Concept], str]
) -> dict[str, tuple[Concept, ...]]:
    """Regroupe les concepts par cle, en ignorant les cles vides.

    La racine ADICAP n'a ni parent ni dictionnaire : la laisser entrer creerait
    un groupe "" trompeur. L'ordre du thesaurus est conserve dans chaque groupe.
    """
    groupes: dict[str, list[Concept]] = {}
    for concept in concepts:
        valeur = cle(concept)
        if valeur:
            groupes.setdefault(valeur, []).append(concept)
    return {valeur: tuple(membres) for valeur, membres in groupes.items()}


@lru_cache(maxsize=1)
def index() -> IndexAdicap:
    """Charge et met en cache l'index ADICAP (un seul acces disque par process)."""
    brut = json.loads(_CHEMIN_INDEX.read_text(encoding="utf-8"))
    if tuple(brut["colonnes"]) != _COLONNES_ATTENDUES:
        raise ValueError(
            f"schema inattendu dans {_CHEMIN_INDEX.name} : {brut['colonnes']}"
        )
    version: str = brut["version"]
    base_uri: str = brut["base_uri"]
    anatomies: dict[str, str] = brut["anatomies"]
    concepts = [_concept(ligne, base_uri, anatomies) for ligne in brut["concepts"]]
    return IndexAdicap(
        version=version,
        base_uri=base_uri,
        par_uri={concept.uri: concept for concept in concepts},
        enfants=_grouper(concepts, lambda c: c.uri_parent),
        par_dictionnaire=_grouper(concepts, lambda c: c.dictionnaire),
        par_code=_grouper(concepts, lambda c: c.code),
    )


def _concurrents(reference: str) -> tuple[Concept, ...]:
    """Concepts dont le CODE vaut `reference` sans que leur URI se termine ainsi.

    Leur existence est ce qui rend la reference courte ambigue : elle se lit
    aussi bien comme un suffixe d'URI que comme un code, et les deux lectures
    ne designent pas le meme concept.
    """
    table = index()
    uri_du_suffixe = table.base_uri + reference
    homonymes = table.par_code.get(reference, ())
    return tuple(c for c in homonymes if c.uri != uri_du_suffixe)


def _uri_complete(reference: str) -> str:
    """Accepte l'URI entiere ou un suffixe NON AMBIGU, et rend l'URI entiere.

    Le raccourci par suffixe est garde parce qu'il est la forme lisible cote
    code, mais il est refuse des qu'il se lit aussi comme le code d'un autre
    concept : rendre l'un des deux au hasard serait une reponse fausse que
    l'appelant n'a aucun moyen de detecter.

    C'est la levee d'ambiguite qui est retenue, PAS l'exigence d'une URI
    systematique : imposer l'URI ne corrigerait rien ici, puisque l'appelant
    qui tient le code "EZ" fabriquerait "<base>EZ" et retomberait exactement
    sur le mauvais concept. Seule la detection de la collision protege. L'URI
    entiere reste donc acceptee telle quelle : la donner, c'est justement
    declarer laquelle des deux lectures on veut.
    """
    reference = reference.strip()
    table = index()
    if reference.startswith(table.base_uri):
        return reference
    uri = table.base_uri + reference
    # Une reference qui ne designe aucun suffixe connu n'est pas ambigue : elle
    # echouera franchement sur un None, ce qui se voit.
    if uri in table.par_uri:
        concurrents = _concurrents(reference)
        if concurrents:
            attendus = ", ".join(f"{c.uri} ({c.libelle})" for c in concurrents[:3])
            raise ValueError(
                f"reference ambigue {reference!r} : suffixe de {uri} "
                f"({table.par_uri[uri].libelle}) mais aussi code de {attendus}. "
                f"Passez l'URI entiere du concept voulu."
            )
    return uri


def concept(reference: str) -> Concept | None:
    """Renvoie le concept d'URI donnee, obsolete compris, ou None s'il est inconnu.

    Volontairement sans filtre d'obsolescence : un compte rendu ancien peut citer
    un code retire et doit rester affichable.

    Leve ValueError si la reference courte est ambigue (voir `_uri_complete`) :
    sur ce module, se tromper de concept est plus grave que s'arreter.
    """
    return index().par_uri.get(_uri_complete(reference))


def enfants(reference: str, *, inclure_obsoletes: bool = False) -> list[Concept]:
    """Fils directs d'un concept, dans l'ordre du thesaurus officiel."""
    fils = index().enfants.get(_uri_complete(reference), ())
    return [c for c in fils if inclure_obsoletes or not c.obsolete]


def lister_dictionnaire(
    code: str, *, inclure_obsoletes: bool = False
) -> list[Concept]:
    """Tous les concepts d'un dictionnaire ('D1'...'D8', 'D8L'), racine exclue."""
    membres = index().par_dictionnaire.get(code.strip().upper(), ())
    return [c for c in membres if inclure_obsoletes or not c.obsolete]


def _rang(libelle_normalise: str, requete: str) -> int | None:
    """Pertinence : 0 identique, 1 commence par, 2 contient, None si hors sujet."""
    if libelle_normalise == requete:
        return 0
    if libelle_normalise.startswith(requete):
        return 1
    if requete in libelle_normalise:
        return 2
    return None


def _candidats(dictionnaire: str, inclure_obsoletes: bool) -> list[Concept]:
    """Perimetre d'une recherche : un dictionnaire precis, ou tout le thesaurus."""
    if dictionnaire:
        return lister_dictionnaire(dictionnaire, inclure_obsoletes=inclure_obsoletes)
    tous = index().par_uri.values()
    return [c for c in tous if inclure_obsoletes or not c.obsolete]


def chercher(
    texte: str,
    *,
    dictionnaire: str = "",
    inclure_obsoletes: bool = False,
    limite: int = _LIMITE_DEFAUT,
) -> list[Concept]:
    """Cherche des concepts par libelle normalise, du plus proche au plus large.

    La comparaison passe des deux cotes par text_utils : sans cela le "SEIN
    (EGALEMENT UTILISE...)" du thesaurus ne repondrait jamais a une dictee
    accentuee, et l'echec serait silencieux. A pertinence egale on prefere le
    libelle le plus court, puis l'URI, pour un resultat stable d'un appel a
    l'autre.
    """
    requete = normaliser(texte).strip()
    if not requete:
        return []
    classes = [
        (rang, len(c.libelle), c.uri, c)
        for c in _candidats(dictionnaire, inclure_obsoletes)
        if (rang := _rang(c.libelle_normalise, requete)) is not None
    ]
    classes.sort(key=lambda ligne: ligne[:3])
    return [ligne[3] for ligne in classes[:limite]]
