"""Routes de la mesure d'ergonomie : le lot du praticien, la lecture de l'admin.

Un fichier a part, un routeur unique pour les deux cotes : le jour ou la mesure
d'usage s'arrete, elle se retire d'une ligne dans main.py sans toucher au reste
de l'instrumentation.

Aucun service tiers n'intervient. Le client agrege lui-meme et depose ses
compteurs ici ; rien ne sort de la base du projet.

Les routes sont minces, comme celles de l'etude : on authentifie, on verifie
que le dossier appartient bien au praticien, et la logique reste dans
etude/ergonomie.py.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from auth import get_admin_user, get_current_user
from database import get_db_session
from db_models import User
from etude.ergonomie import (
    ReleveObserve,
    ReleveZone,
    agreger,
    enregistrer_releves,
)
from etude.models import EtudeDossier, EtudeErgonomie, EtudeSession
from etude.service import EtudeRefus

router = APIRouter(tags=["etude-ergonomie"])

Utilisateur = Annotated[User, Depends(get_current_user)]
Admin = Annotated[User, Depends(get_admin_user)]
Base = Annotated[AsyncSession | None, Depends(get_db_session)]


# ---------------------------------------------------------------------------
# Modeles d'echange
# ---------------------------------------------------------------------------


class ZoneMesuree(BaseModel):
    """Les compteurs d'une zone, cumules depuis l'ouverture du dossier.

    Cumules et non incrementaux : c'est ce qui rend un lot perdu inoffensif.
    Le depouillement ne garde que le dernier instantane de chaque zone.
    """

    zone: str
    visible_ms: int = 0
    clics: int = 0
    profondeur_max: float | None = None
    rang_premiere_visite: int | None = None
    part_largeur: float | None = None


class LotErgonomie(BaseModel):
    """Un lot d'instantanes. Le client envoie toutes ses zones d'un coup."""

    releves: list[ZoneMesuree] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Garde-fous
# ---------------------------------------------------------------------------


def _exiger_base(db: AsyncSession | None) -> AsyncSession:
    if db is None:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, "Base de donnees non disponible."
        )
    return db


async def _verifier_le_dossier(
    db: AsyncSession, dossier_id: str, praticien_id: str
) -> None:
    """Refuse de mesurer l'ecran d'un autre praticien."""
    dossier = await db.get(EtudeDossier, dossier_id)
    if dossier is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Dossier introuvable.")
    session = await db.get(EtudeSession, dossier.session_id)
    if session is None or session.praticien_id != praticien_id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Dossier d'un autre praticien.")


# ---------------------------------------------------------------------------
# Depot du lot
# ---------------------------------------------------------------------------


@router.post("/etude/dossiers/{dossier_id}/ergonomie")
async def deposer_lot(
    dossier_id: str, corps: LotErgonomie, user: Utilisateur, db: Base
) -> dict[str, int]:
    """Enregistre un lot d'instantanes d'usage pour un dossier.

    Un lot vide est accepte sans ecrire : le client envoie a periode fixe, et
    une periode sans rien a dire n'est pas une erreur.
    """
    base = _exiger_base(db)
    await _verifier_le_dossier(base, dossier_id, user.id)
    try:
        ecrits = await enregistrer_releves(
            base,
            dossier_id,
            [
                ReleveZone(
                    zone=mesure.zone,
                    visible_ms=mesure.visible_ms,
                    clics=mesure.clics,
                    profondeur_max=mesure.profondeur_max,
                    rang_premiere_visite=mesure.rang_premiere_visite,
                    part_largeur=mesure.part_largeur,
                )
                for mesure in corps.releves
            ],
        )
    except EtudeRefus as refus:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(refus)) from refus
    return {"releves_enregistres": ecrits}


# ---------------------------------------------------------------------------
# Lecture par l'administration
# ---------------------------------------------------------------------------


@router.get("/admin/etude/ergonomie")
async def profil_d_usage(_admin: Admin, db: Base) -> dict[str, object]:
    """Le profil d'usage de l'interface, zone par zone, avec ses denominateurs.

    Les dossiers exclus (essais, saisies aberrantes) n'entrent dans aucun
    calcul : une exclusion qui n'exclut pas donnerait l'illusion d'un corpus
    propre, ici comme sur les taux de decision.
    """
    base = _exiger_base(db)
    resultat = await base.execute(
        select(EtudeErgonomie)
        .join(EtudeDossier, EtudeErgonomie.dossier_id == EtudeDossier.id)
        .where(EtudeDossier.exclu.is_(False))
    )
    return agreger([_observe(ligne) for ligne in resultat.scalars().all()])


def _observe(ligne: EtudeErgonomie) -> ReleveObserve:
    return ReleveObserve(
        dossier_id=ligne.dossier_id,
        zone=ligne.zone,
        visible_ms=ligne.visible_ms,
        clics=ligne.clics,
        profondeur_max=ligne.profondeur_max,
        rang_premiere_visite=ligne.rang_premiere_visite,
        part_largeur=ligne.part_largeur,
        releve_a=ligne.releve_a,
    )
