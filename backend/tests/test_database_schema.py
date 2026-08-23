"""Rattrapage des colonnes manquantes au demarrage.

`create_all` cree les tables qui manquent et ne touche jamais a celles qui
existent. Une colonne ajoutee au modele apres un premier deploiement n'apparait
donc nulle part : l'application demarre sans rien dire, puis rend une erreur 500
au premier SELECT. C'est arrive en production sur `etude_propositions`, et ces
tests sont la pour que ca n'arrive plus.
"""

from __future__ import annotations

import pytest
import pytest_asyncio
from sqlalchemy import Column, MetaData, String, Table, inspect, select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import etude.models  # noqa: F401  (enregistre les tables sur Base)
from database import _reconcilier
from db_models import Base
from etude.models import EtudeProposition


@pytest_asyncio.fixture
async def moteur(tmp_path):
    """Base au SCHEMA D'AVANT : la colonne recente n'existe pas."""
    moteur = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'drift.db'}")
    async with moteur.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.execute(
            text("ALTER TABLE etude_propositions DROP COLUMN nature_correction")
        )
    yield moteur
    await moteur.dispose()


async def test_le_schema_derive_casse_la_lecture(moteur):
    """Le symptome, reproduit : sans ce test, la correction ne prouverait rien."""
    fabrique = async_sessionmaker(moteur, expire_on_commit=False)
    async with fabrique() as session:
        with pytest.raises(Exception, match="nature_correction"):
            await session.execute(select(EtudeProposition))


async def test_le_demarrage_rattrape_la_colonne(moteur):
    async with moteur.begin() as conn:
        await conn.run_sync(_reconcilier)

    fabrique = async_sessionmaker(moteur, expire_on_commit=False)
    async with fabrique() as session:
        await session.execute(select(EtudeProposition))


async def test_le_rattrapage_est_idempotent(moteur):
    """Il tourne a CHAQUE demarrage : un second passage ne doit rien tenter."""
    async with moteur.begin() as conn:
        await conn.run_sync(_reconcilier)
        await conn.run_sync(_reconcilier)


async def test_le_rattrapage_ne_detruit_rien(moteur):
    """Strictement additif : aucune colonne existante ne doit disparaitre ni
    changer de type. Une base de production contient des donnees d'etude qu'on
    ne peut pas reconstituer."""
    def _colonnes(connexion) -> dict[str, str]:
        return {
            c["name"]: str(c["type"])
            for c in inspect(connexion).get_columns("etude_propositions")
        }

    async with moteur.begin() as conn:
        avant = await conn.run_sync(_colonnes)
        await conn.run_sync(_reconcilier)
        apres = await conn.run_sync(_colonnes)

    assert set(avant) < set(apres), "la colonne manquante n'a pas ete ajoutee"
    for nom, type_avant in avant.items():
        assert apres[nom] == type_avant, f"{nom} a change de type"


async def test_une_colonne_obligatoire_est_signalee_et_non_forcee(moteur, caplog):
    """Une colonne NOT NULL ne peut pas s'ajouter sans valeur de remplissage :
    la forcer echouerait ou remplirait la base de valeurs inventees. On la
    signale et on laisse la main a une vraie migration."""
    metadata = MetaData()
    Table(
        "etude_propositions", metadata,
        Column("id", String(36), primary_key=True),
        Column("colonne_obligatoire", String(10), nullable=False),
    )
    with caplog.at_level("ERROR"):
        async with moteur.begin() as conn:
            await conn.run_sync(_reconcilier, metadata)
    assert "colonne_obligatoire" in caplog.text
    assert "migration" in caplog.text.lower()
