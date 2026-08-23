"""Route d'export des donnees de l'etude.

Le proprietaire l'a demande dans ces termes : « j'espere que ces datas-la on
pourra les recuperer et les exporter en CSV et tout ca ». Aucun depouillement
serieux ne se fait dans un navigateur — sans cette route, les donnees sont
consultables mais pas analysables.

Une seule route, reservee a l'administrateur, qui sert une archive ZIP des
quatre tables a plat plus son dictionnaire de donnees. Un fichier a part du
reste de l'administration : l'export sert un autre besoin (sortir les donnees)
que la synthese (les regarder), et les deux se retirent independamment.
"""

from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from auth import get_admin_user
from database import get_db_session
from db_models import User
from etude.export import (
    charger_corpus,
    construire_archive,
    construire_classeur,
    nom_archive,
    nom_classeur,
)

router = APIRouter(prefix="/admin/etude", tags=["admin-etude"])

Admin = Annotated[User, Depends(get_admin_user)]
Base = Annotated[AsyncSession | None, Depends(get_db_session)]

TYPE_ZIP = "application/zip"


def _exiger_base(db: AsyncSession | None) -> AsyncSession:
    """Refuse d'exporter sans base plutot que de servir une archive vide.

    Une archive de quatre fichiers vides ressemble trait pour trait a une
    etude sans donnees : il faut dire que la base manque, pas laisser croire
    que rien n'a ete recueilli.
    """
    if db is None:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, "Base de donnees non disponible."
        )
    return db


@router.get("/export")
async def exporter(_admin: Admin, db: Base) -> Response:
    """Sert les donnees de l'etude en une archive ZIP de quatre CSV.

    Les dossiers exclus y figurent, avec leur motif : c'est a l'analyse de
    filtrer, pas a l'export de cacher. Les praticiens y sont pseudonymises de
    facon stable, pour qu'on puisse recouper deux exports sans jamais
    manipuler de nom.
    """
    base = _exiger_base(db)
    moment = datetime.now(timezone.utc)
    archive = construire_archive(await charger_corpus(base), moment)
    return Response(
        content=archive,
        media_type=TYPE_ZIP,
        headers={
            "Content-Disposition": f'attachment; filename="{nom_archive(moment)}"'
        },
    )


@router.get("/export.xlsx")
async def exporter_classeur(_admin: Admin, db: Base) -> Response:
    """Sert les memes donnees en classeur Excel, un onglet par table.

    Le CSV reste le format d'ANALYSE — il se lit partout et ne deforme rien. Le
    classeur est le format de TRAVAIL, celui qu'on ouvre pour regarder et
    montrer. Servir les deux evite de perdre l'un des deux publics ; ils portent
    les memes lignes, donc ils se recoupent.
    """
    base = _exiger_base(db)
    corpus = await charger_corpus(base)
    moment = datetime.now(timezone.utc)
    return Response(
        content=construire_classeur(corpus, moment),
        media_type=(
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        ),
        headers={
            "Content-Disposition": f'attachment; filename="{nom_classeur(moment)}"'
        },
    )
