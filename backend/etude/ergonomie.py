"""Mesure de l'ergonomie reelle, sans traceur tiers.

La question posee par le proprietaire : jusqu'ou defile-t-on, ou regarde-t-on,
ou clique-t-on ? Elle se resout d'ordinaire avec un service d'analyse
d'audience. Pas ici : le produit se vend sur la souverainete des donnees, et
brancher un traceur etranger sur un outil medical annulerait l'argument, meme
sans donnee patient. Tout ce qui suit tient donc dans la base du projet.

CE QUI EST MESURE, et rien de plus :

  - la profondeur de defilement atteinte par zone (part du contenu vue) ;
  - le temps passe avec chaque zone a l'ecran ;
  - les clics par zone nommee ;
  - l'ordre de premiere visite : par ou commence-t-on ?
  - la part de largeur donnee a chaque zone — le partage choisi a la glissiere
    est une mesure d'ergonomie a lui seul.

CE QUI NE L'EST PAS : le contenu saisi, la position du curseur au pixel, les
frappes. On mesure des comportements d'usage, pas ce que le praticien ecrit.

L'INSTANTANE PLUTOT QUE L'INCREMENT. Le client agrege et envoie par lots l'etat
COURANT de ses compteurs. Le depouillement ne retient que le dernier instantane
de chaque couple (dossier, zone) : un lot perdu ne coute alors que du detail,
jamais un total, et un lot rejoue ne compte rien deux fois. La mesure peut
echouer sans jamais fausser ce qu'elle mesure.

Les trois regles de l'etude s'appliquent ici comme partout : un taux montre son
denominateur, un denominateur nul donne None et jamais zero, et les dossiers
exclus n'entrent dans aucun calcul (le filtre est pose par l'appelant, qui seul
connait la base).
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from typing import Final

from sqlalchemy.ext.asyncio import AsyncSession

from etude.analyse import Taux, moyenne
from etude.models import EtudeErgonomie
from etude.service import EtudeRefus

# --- Zones nommees ---------------------------------------------------------
#
# Des NOMS, jamais des selecteurs CSS : un selecteur change au premier
# remaniement de l'interface et la serie de mesures se coupe en deux sans que
# rien ne le signale. Le nom, lui, survit au remaniement.

ZONE_ANALYSE: Final = "analyse"
ZONE_COMPTE_RENDU: Final = "compte_rendu"
ZONE_BARRE_AJOUT: Final = "barre_ajout"
ZONE_VALIDATION: Final = "validation"

#: Ordonnees pour que le tableau servi a l'administration garde le meme ordre
#: d'une lecture a l'autre.
ZONES: Final[tuple[str, ...]] = (
    ZONE_ANALYSE,
    ZONE_COMPTE_RENDU,
    ZONE_BARRE_AJOUT,
    ZONE_VALIDATION,
)


def zone_valide(zone: str) -> bool:
    """La zone appartient-elle au vocabulaire de la mesure ?"""
    return zone in ZONES


# --- Ce que le client envoie -----------------------------------------------


@dataclass(frozen=True)
class ReleveZone:
    """Les compteurs d'une zone a un instant, cumules depuis l'ouverture."""

    zone: str
    visible_ms: int
    clics: int
    profondeur_max: float | None = None
    rang_premiere_visite: int | None = None
    part_largeur: float | None = None


def _part_bornee(valeur: float | None) -> float | None:
    """Ramene une part dans [0, 1], et laisse None ce qui n'a pas ete mesure.

    On borne au lieu de refuser : une part aberrante vient d'un arrondi de
    navigateur, pas d'une fraude, et perdre tout un lot pour un centieme de
    trop couterait plus que la valeur ne vaut.
    """
    if valeur is None:
        return None
    return round(min(1.0, max(0.0, valeur)), 4)


def _compteur_borne(valeur: int) -> int:
    """Un compteur cumule ne peut pas etre negatif."""
    return max(0, valeur)


def _rang_borne(valeur: int | None) -> int | None:
    """Un rang de visite commence a 1 ; zero n'est pas un rang, c'est une absence."""
    if valeur is None or valeur < 1:
        return None
    return valeur


def _vers_ligne(dossier_id: str, releve: ReleveZone) -> EtudeErgonomie:
    """Convertit un instantane client en ligne de base, valeurs bornees."""
    return EtudeErgonomie(
        dossier_id=dossier_id,
        zone=releve.zone,
        visible_ms=_compteur_borne(releve.visible_ms),
        clics=_compteur_borne(releve.clics),
        profondeur_max=_part_bornee(releve.profondeur_max),
        rang_premiere_visite=_rang_borne(releve.rang_premiere_visite),
        part_largeur=_part_bornee(releve.part_largeur),
    )


async def enregistrer_releves(
    db: AsyncSession | None, dossier_id: str, releves: list[ReleveZone]
) -> int:
    """Ecrit un lot d'instantanes et rend le nombre de lignes ecrites.

    Une zone hors vocabulaire fait refuser le LOT ENTIER, au lieu d'etre
    ecartee en silence. Une zone silencieusement ecartee ressemblerait, au
    depouillement, a un panneau que personne n'a jamais visite : on lirait un
    resultat d'ergonomie la ou il n'y a qu'un nom mal cable.
    """
    if db is None:
        return 0
    inconnues = sorted({r.zone for r in releves if not zone_valide(r.zone)})
    if inconnues:
        raise EtudeRefus(f"Zone d'ergonomie inconnue : {', '.join(inconnues)}.")
    for releve in releves:
        db.add(_vers_ligne(dossier_id, releve))
    await db.commit()
    return len(releves)


# --- Ce que la base rend ---------------------------------------------------


@dataclass(frozen=True)
class ReleveObserve:
    """Un instantane relu en base, rattache a son dossier et a sa date.

    Une structure de lecture plutot que l'ORM : l'agregation se teste alors
    sans base, comme le reste du depouillement.
    """

    dossier_id: str
    zone: str
    visible_ms: int
    clics: int
    profondeur_max: float | None
    rang_premiere_visite: int | None
    part_largeur: float | None
    releve_a: datetime


def _remplace(candidat: ReleveObserve, retenu: ReleveObserve) -> bool:
    """Le candidat est-il plus recent que l'instantane deja retenu ?

    L'horodatage tranche, sauf a egalite — et l'egalite arrive : SQLite date a
    la seconde, deux lots envoyes dans la meme seconde portent la meme heure.
    On departage alors par le temps cumule, parce qu'un compteur cumule ne peut
    que croitre : le plus fourni est forcement le plus tardif. Sans cette regle,
    l'ordre des lignes rendues par la base deciderait, et un instantane plus
    ancien pourrait effacer un plus complet.
    """
    if candidat.releve_a != retenu.releve_a:
        return candidat.releve_a > retenu.releve_a
    return candidat.visible_ms >= retenu.visible_ms


def dernier_par_zone(
    releves: list[ReleveObserve],
) -> dict[tuple[str, str], ReleveObserve]:
    """Ne garde que l'instantane le plus recent de chaque (dossier, zone).

    C'est LA regle de lecture de cette table. Les compteurs sont cumules depuis
    l'ouverture du dossier : les sommer compterait les memes secondes autant de
    fois que le client a envoye un lot.
    """
    retenus: dict[tuple[str, str], ReleveObserve] = {}
    for releve in releves:
        cle = (releve.dossier_id, releve.zone)
        retenu = retenus.get(cle)
        if retenu is None or _remplace(releve, retenu):
            retenus[cle] = releve
    return retenus


# --- Profil d'usage --------------------------------------------------------


@dataclass(frozen=True)
class ProfilZone:
    """Ce qu'on sait de l'usage d'une zone, avec les denominateurs.

    Trois denominateurs distincts, et ce n'est pas une coquetterie : une zone
    peut avoir ete observee sur cinquante dossiers, n'avoir de profondeur
    mesurable que sur douze (ailleurs elle tenait dans l'ecran) et de partage de
    largeur que sur ceux ou elle partageait l'ecran. Un seul denominateur pour
    les trois moyennes ferait passer une mesure absente pour une mesure faite.
    """

    zone: str
    #: Dossiers ou la zone a ete observee : denominateur du temps et des clics.
    nb_dossiers: int
    temps_visible_ms_moyen: float | None
    clics_moyens: float | None
    profondeur_moyenne: float | None
    nb_dossiers_profondeur: int
    part_largeur_moyenne: float | None
    nb_dossiers_largeur: int
    #: Part des dossiers ou c'est par cette zone que le praticien a commence.
    premiere_visite: Taux

    def en_dict(self) -> dict[str, object]:
        return {
            "zone": self.zone,
            "nb_dossiers": self.nb_dossiers,
            "temps_visible_ms_moyen": self.temps_visible_ms_moyen,
            "clics_moyens": self.clics_moyens,
            "profondeur_moyenne": self.profondeur_moyenne,
            "nb_dossiers_profondeur": self.nb_dossiers_profondeur,
            "part_largeur_moyenne": self.part_largeur_moyenne,
            "nb_dossiers_largeur": self.nb_dossiers_largeur,
            "premiere_visite": self.premiere_visite.en_dict(),
        }


def _profil_zone(
    zone: str, releves: list[ReleveObserve], nb_dossiers_commences: int
) -> ProfilZone:
    """Assemble le profil d'une zone a partir de ses derniers instantanes."""
    profondeurs = [r.profondeur_max for r in releves if r.profondeur_max is not None]
    largeurs = [r.part_largeur for r in releves if r.part_largeur is not None]
    return ProfilZone(
        zone=zone,
        nb_dossiers=len(releves),
        temps_visible_ms_moyen=moyenne([float(r.visible_ms) for r in releves]),
        clics_moyens=moyenne([float(r.clics) for r in releves]),
        profondeur_moyenne=moyenne(profondeurs),
        nb_dossiers_profondeur=len(profondeurs),
        part_largeur_moyenne=moyenne(largeurs),
        nb_dossiers_largeur=len(largeurs),
        premiere_visite=Taux(
            sum(1 for r in releves if r.rang_premiere_visite == 1),
            nb_dossiers_commences,
            f"Dossiers commences par « {zone} »",
        ),
    )


def _dossiers_commences(retenus: dict[tuple[str, str], ReleveObserve]) -> int:
    """Dossiers ou une premiere visite a bien ete observee.

    Denominateur de l'ordre de visite, et lui seul : un dossier ou aucun geste
    n'a ete date ne dit rien sur le point de depart. L'inclure au denominateur
    ferait baisser toutes les parts sans qu'aucune observation ne le justifie.
    """
    return len(
        {
            releve.dossier_id
            for releve in retenus.values()
            if releve.rang_premiere_visite is not None
        }
    )


def agreger(releves: list[ReleveObserve]) -> dict[str, object]:
    """Profil d'usage par zone, sur les dossiers fournis.

    L'appelant a deja ecarte les dossiers exclus : le filtre demande la base, ce
    module n'en connait pas.
    """
    retenus = dernier_par_zone(releves)
    commences = _dossiers_commences(retenus)
    par_zone: dict[str, list[ReleveObserve]] = {zone: [] for zone in ZONES}
    for releve in retenus.values():
        if releve.zone in par_zone:
            par_zone[releve.zone].append(releve)

    return {
        "nb_dossiers_mesures": len({r.dossier_id for r in retenus.values()}),
        "nb_dossiers_commences": commences,
        "zones": [
            _profil_zone(zone, par_zone[zone], commences).en_dict() for zone in ZONES
        ],
        "ordre_de_depart": _ordre_de_depart(retenus),
    }


def _ordre_de_depart(retenus: dict[tuple[str, str], ReleveObserve]) -> dict[str, int]:
    """Effectifs par zone de depart : par ou commence-t-on, en clair.

    Le meme fait que `premiere_visite`, servi en effectifs bruts. Un lecteur qui
    veut refaire le calcul ne doit pas avoir a remultiplier des parts.
    """
    depart = Counter(
        releve.zone for releve in retenus.values() if releve.rang_premiere_visite == 1
    )
    return {zone: depart[zone] for zone in ZONES if depart[zone] > 0}
