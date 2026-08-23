"""Configuration de la connexion base de donnees PostgreSQL.

Fournit le moteur async SQLAlchemy et la session factory.
En mode developpement sans BDD, les operations sont silencieusement ignorees.
"""

import logging
from collections.abc import AsyncGenerator

from sqlalchemy import inspect as sa_inspect
from sqlalchemy import literal, text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from config import get_settings
from db_models import Base

# Les tables de l'etude s'enregistrent sur la meme Base a l'import.
import etude.models  # noqa: F401,E402

logger = logging.getLogger("anapath.db")


def _create_engine() -> AsyncEngine | None:
    """Cree le moteur async SQLAlchemy si DATABASE_URL est configure."""
    settings = get_settings()
    if not settings.database_url:
        return None

    is_sqlite: bool = settings.database_url.startswith("sqlite")
    kwargs: dict[str, object] = {"echo": False}

    if not is_sqlite:
        kwargs["pool_size"] = 5
        kwargs["max_overflow"] = 10

    return create_async_engine(settings.database_url, **kwargs)


_engine: AsyncEngine | None = _create_engine()

_session_factory: async_sessionmaker[AsyncSession] | None = (
    async_sessionmaker(_engine, expire_on_commit=False)
    if _engine is not None
    else None
)


async def get_db_session() -> AsyncGenerator[AsyncSession | None, None]:
    """Dependency FastAPI : fournit une session DB ou None si pas de BDD."""
    if _session_factory is None:
        yield None
        return
    async with _session_factory() as session:
        yield session


def _colonnes_manquantes(connexion, table) -> list:
    """Colonnes decrites par le modele et absentes de la base.

    `create_all` cree les tables qui manquent, mais ne touche JAMAIS a une
    table qui existe deja. Une colonne ajoutee au modele apres un premier
    deploiement n'apparait donc nulle part — et l'application demarre sans rien
    dire, puis rend une erreur 500 au premier SELECT. C'est arrive en
    production sur `etude_propositions`.
    """
    inspecteur = sa_inspect(connexion)
    if not inspecteur.has_table(table.name):
        return []
    presentes = {colonne["name"] for colonne in inspecteur.get_columns(table.name)}
    return [colonne for colonne in table.columns if colonne.name not in presentes]


def _defaut_sql(colonne, dialecte) -> str | None:
    """Le defaut de la colonne, ecrit comme litteral SQL. None s'il n'y en a pas."""
    defaut = colonne.default
    if defaut is None or not getattr(defaut, "is_scalar", False):
        return None
    return str(
        literal(defaut.arg).compile(
            dialect=dialecte, compile_kwargs={"literal_binds": True}
        )
    )


def _clause_ajout(colonne, dialecte) -> str | None:
    """La clause ADD COLUMN, ou None si la colonne ne peut pas etre ajoutee seule.

    Une colonne OBLIGATOIRE avec un defaut s'ajoute sans risque : les lignes
    existantes prennent ce defaut, qui est celui que le modele leur donnerait de
    toute facon. La refuser bloquait le demarrage sur un ALTER parfaitement sur —
    et c'est ce qui a produit une erreur 500 en production sur `etude_dossiers`.

    Une colonne obligatoire SANS defaut, elle, reste refusee : il faudrait
    inventer une valeur pour les lignes existantes, et cette decision appartient
    a une migration, pas a un demarrage.
    """
    type_sql = colonne.type.compile(dialecte)
    if colonne.nullable:
        return f'"{colonne.name}" {type_sql}'
    defaut = _defaut_sql(colonne, dialecte)
    if defaut is None:
        return None
    return f'"{colonne.name}" {type_sql} NOT NULL DEFAULT {defaut}'


def _reconcilier(connexion, metadata=None) -> None:
    """Ajoute les colonnes manquantes, sans jamais rien detruire.

    STRICTEMENT ADDITIF, et seulement sur des colonnes NULLABLES : on n'altere
    aucun type, on ne renomme rien, on ne supprime rien. Une colonne obligatoire
    ne peut pas s'ajouter sans valeur de remplissage, donc elle est signalee et
    laissee a une vraie migration.

    C'est un filet, pas un remplacement d'Alembic : il rattrape l'ajout de
    colonne, qui est le cas courant, et il refuse tout le reste bruyamment.

    `metadata` n'existe que pour les tests : sans lui, ils devraient modifier le
    registre global des tables, qui est immuable et partage.
    """
    dialecte = connexion.dialect
    for table in (metadata or Base.metadata).sorted_tables:
        for colonne in _colonnes_manquantes(connexion, table):
            clause = _clause_ajout(colonne, dialecte)
            if clause is None:
                logger.error(
                    "Colonne %s.%s absente en base, obligatoire et SANS defaut : "
                    "migration requise, aucune valeur ne peut etre inventee.",
                    table.name, colonne.name,
                )
                continue
            connexion.execute(
                text(f'ALTER TABLE "{table.name}" ADD COLUMN {clause}')
            )
            logger.warning("Colonne ajoutee a chaud : %s.%s.", table.name, colonne.name)


async def create_tables() -> None:
    """Cree les tables manquantes, puis rattrape les colonnes manquantes."""
    if _engine is None:
        return

    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.run_sync(_reconcilier)


async def close_engine() -> None:
    """Ferme le moteur async a l'arret de l'application."""
    if _engine is not None:
        await _engine.dispose()
