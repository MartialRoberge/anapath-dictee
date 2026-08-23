"""Ecritures de l'instrumentation : les invariants de la mesure.

Chaque test protege une donnee qu'on ne pourrait pas reconstituer apres coup.
Une erreur ici ne se voit qu'au depouillement, quand il est trop tard.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import etude.models  # noqa: F401  (enregistre les tables sur Base)
from db_models import Base, User
from etude.extraction import PropositionExtraite
from etude.models import (
    EtudeDossier,
    EtudePause,
    EtudePrelevement,
    EtudeProposition,
)
from etude.service import (
    EtudeRefus,
    abandonner_dossier,
    clore_dossier,
    distance_edition,
    enregistrer_decision,
    enregistrer_pause,
    enregistrer_prelevements,
    enregistrer_reponses,
    ouvrir_dossier,
    ouvrir_session,
)
from etude.vocabulaire import (
    SEUIL_HATIVE_MOTS,
    TYPE_COMPLETUDE,
    TYPE_RESTITUTION,
)

PRATICIEN = "praticien-test"


@pytest_asyncio.fixture
async def db():
    """Base en memoire, schema complet, un praticien insere."""
    moteur = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with moteur.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    fabrique = async_sessionmaker(moteur, expire_on_commit=False)
    async with fabrique() as session:
        session.add(
            User(
                id=PRATICIEN,
                email="praticien@marc.test",
                password_hash="x",
                name="Praticien",
            )
        )
        await session.commit()
        yield session
    await moteur.dispose()


def _proposition(valeur: str, type_proposition: str = TYPE_RESTITUTION):
    return PropositionExtraite(
        type_proposition=type_proposition,
        sous_type="conclusion",
        valeur_proposee=valeur,
        empan_debut=0,
        empan_fin=10,
        empan_extrait="dictee ici",
        longueur_mots=len(valeur.split()),
    )


async def _lignes(db, modele, dossier_id):
    """Lit les filles d'un dossier par requete explicite.

    Traverser la relation ferait un lazy-load, interdit sur une session async.
    """
    resultat = await db.execute(
        select(modele).where(modele.dossier_id == dossier_id).order_by(modele.id)
    )
    return list(resultat.scalars().all())


async def _dossier_avec(db, propositions):
    session = await ouvrir_session(db, PRATICIEN)
    assert session is not None
    return await ouvrir_dossier(
        db,
        session_id=session.id,
        transcription="dictee ici, colon sigmoide",
        cr_propose="**Conclusion :**\nAdenome tubuleux.",
        propositions=propositions,
    )


# --- L'invariant central : le texte propose ne se reecrit pas --------------


async def test_le_cr_propose_survit_a_la_cloture(db):
    """Sans le texte propose a cote du texte valide, la charge d'edition n'est
    pas calculable — et c'est irrattrapable apres coup."""
    dossier = await _dossier_avec(db, [_proposition("Adenome tubuleux")])
    assert dossier is not None
    propose = dossier.cr_propose

    await clore_dossier(db, dossier.id, cr_valide="Adenocarcinome infiltrant.")

    relu = await db.get(EtudeDossier, dossier.id)
    assert relu.cr_propose == propose
    assert relu.cr_valide == "Adenocarcinome infiltrant."


async def test_la_charge_d_edition_est_calculee_a_la_cloture(db):
    dossier = await _dossier_avec(db, [])
    await clore_dossier(db, dossier.id, cr_valide=dossier.cr_propose)
    relu = await db.get(EtudeDossier, dossier.id)
    assert relu.caracteres_modifies == 0


def test_un_cr_accepte_tel_quel_donne_zero():
    """C'est la seule mesure qui compte pour le praticien."""
    assert distance_edition("Adenome tubuleux.", "Adenome tubuleux.") == 0
    assert distance_edition("Adenome", "Adenocarcinome") > 0


# --- Les grilles de decision ----------------------------------------------


async def test_une_decision_hors_grille_est_refusee(db):
    """Ecrire 'non_dicte' sur une completude fausserait le taux
    d'hallucination : c'est la grille de restitution."""
    dossier = await _dossier_avec(
        db, [_proposition("Grade histopronostique", TYPE_COMPLETUDE)]
    )
    proposition = (await _lignes(db, EtudeProposition, dossier.id))[0]

    with pytest.raises(EtudeRefus):
        await enregistrer_decision(db, proposition.id, "non_dicte")

    await enregistrer_decision(db, proposition.id, "non_pertinent")
    assert (await db.get(EtudeProposition, proposition.id)).decision == "non_pertinent"


async def test_une_cause_d_erreur_inconnue_est_refusee(db):
    dossier = await _dossier_avec(db, [_proposition("Adenome tubuleux")])
    proposition = (await _lignes(db, EtudeProposition, dossier.id))[0]
    with pytest.raises(EtudeRefus):
        await enregistrer_decision(
            db, proposition.id, "corrige", cause_erreur="fatigue"
        )


# --- Telemetrie de decision ------------------------------------------------


async def test_la_latence_est_calculee_cote_serveur(db):
    """Une latence fournie par le client pourrait etre rendue flatteuse, et
    c'est elle qui fonde le marquage hative."""
    dossier = await _dossier_avec(db, [_proposition("Adenome tubuleux")])
    proposition = (await _lignes(db, EtudeProposition, dossier.id))[0]

    decidee = await enregistrer_decision(db, proposition.id, "conforme")
    assert decidee.latence_ms is not None
    assert decidee.latence_ms >= 0


async def test_une_decision_immediate_sur_un_long_texte_est_hative(db):
    """Le verrou d'export cree une pression a cliquer vite : sans ce marqueur,
    il fabrique un taux de completion de 100 % qui ne veut rien dire."""
    longue = " ".join(["mot"] * (SEUIL_HATIVE_MOTS + 5))
    dossier = await _dossier_avec(db, [_proposition(longue)])
    proposition = (await _lignes(db, EtudeProposition, dossier.id))[0]

    decidee = await enregistrer_decision(db, proposition.id, "conforme")
    assert decidee.hative is True


async def test_une_decision_immediate_sur_un_texte_court_ne_l_est_pas(db):
    dossier = await _dossier_avec(db, [_proposition("Adenome tubuleux")])
    proposition = (await _lignes(db, EtudeProposition, dossier.id))[0]
    decidee = await enregistrer_decision(db, proposition.id, "conforme")
    assert decidee.hative is False


async def test_le_changement_d_avis_apres_justification_est_trace(db):
    """LA metrique d'explicabilite : la justification a-t-elle change l'avis ?
    Elle ne se mesure qu'au moment ou l'avis change."""
    dossier = await _dossier_avec(db, [_proposition("Adenome tubuleux")])
    proposition = (await _lignes(db, EtudeProposition, dossier.id))[0]

    await enregistrer_decision(db, proposition.id, "conforme")
    apres = await enregistrer_decision(
        db, proposition.id, "corrige", justif_ouverte=True, justif_duree_ms=4200
    )
    assert apres.decision_changee_apres_justif is True
    assert apres.justif_duree_ms == 4200


async def test_une_decision_confirmee_ne_compte_pas_comme_un_changement(db):
    dossier = await _dossier_avec(db, [_proposition("Adenome tubuleux")])
    proposition = (await _lignes(db, EtudeProposition, dossier.id))[0]
    await enregistrer_decision(db, proposition.id, "conforme")
    apres = await enregistrer_decision(
        db, proposition.id, "conforme", justif_ouverte=True
    )
    assert apres.decision_changee_apres_justif is False


async def test_t3_et_t4_encadrent_les_decisions(db):
    dossier = await _dossier_avec(
        db, [_proposition("Adenome tubuleux"), _proposition("Limites saines")]
    )
    propositions = await _lignes(db, EtudeProposition, dossier.id)
    await enregistrer_decision(db, propositions[0].id, "conforme")
    await enregistrer_decision(db, propositions[1].id, "conforme")

    relu = await db.get(EtudeDossier, dossier.id)
    assert relu.t3_premiere_decision is not None
    assert relu.t4_derniere_decision is not None
    assert relu.t3_premiere_decision <= relu.t4_derniere_decision


# --- Pauses, abandon, prelevements ----------------------------------------


async def test_une_pause_est_journalisee_pas_seulement_soustraite(db):
    """Leur nombre et leur duree sont eux-memes un resultat sur la faisabilite
    en conditions reelles."""
    dossier = await _dossier_avec(db, [])
    debut = datetime.now(UTC)
    await enregistrer_pause(
        db, dossier.id, debut, debut + timedelta(seconds=120), "inactivite"
    )
    pauses = await _lignes(db, EtudePause, dossier.id)
    assert len(pauses) == 1
    assert isinstance(pauses[0], EtudePause)
    assert pauses[0].duree_ms == 120_000


async def test_une_cause_de_pause_inconnue_est_refusee(db):
    dossier = await _dossier_avec(db, [])
    debut = datetime.now(UTC)
    with pytest.raises(EtudeRefus):
        await enregistrer_pause(db, dossier.id, debut, debut, "cafe")


async def test_un_dossier_abandonne_ne_peut_plus_etre_clos(db):
    """L'abandon est une porte de sortie : sans elle, un praticien bloque
    valide par complaisance et l'etude est fausse tout en paraissant parfaite."""
    dossier = await _dossier_avec(db, [])
    await abandonner_dossier(db, dossier.id, "outil_trop_lent")
    with pytest.raises(EtudeRefus):
        await clore_dossier(db, dossier.id, cr_valide="peu importe")


async def test_un_motif_d_abandon_inconnu_est_refuse(db):
    dossier = await _dossier_avec(db, [])
    with pytest.raises(EtudeRefus):
        await abandonner_dossier(db, dossier.id, "flemme")


async def test_chaque_prelevement_porte_ses_propres_codes(db):
    """Cette cardinalite EST la correction du bug de terrain : un code juste
    et un code faux dans le meme dossier font deux mesures, pas une moyenne."""
    dossier = await _dossier_avec(db, [])
    await enregistrer_prelevements(
        db,
        dossier.id,
        [
            {"libelle": "Colon sigmoide", "codes": [{"code": "BHGS0030", "role": "primaire"}]},
            {"libelle": "Ganglion", "codes": [{"code": "BHGS0100", "role": "primaire"}]},
        ],
    )
    relu = await db.get(EtudeDossier, dossier.id)
    prelevements = await _lignes(db, EtudePrelevement, dossier.id)
    assert len(prelevements) == 2
    assert relu.nb_prelevements_detecte == 2
    assert sorted(p.rang for p in prelevements) == [1, 2]


# --- Questionnaires --------------------------------------------------------


async def test_un_questionnaire_inconnu_est_refuse(db):
    with pytest.raises(EtudeRefus):
        await enregistrer_reponses(db, PRATICIEN, "sus_maison", {"a": "1"})


async def test_chaque_item_est_une_ligne(db):
    """Le depouillement se fait sans parser, et un item peut etre retire en
    cours de rodage sans migration."""
    ecrites = await enregistrer_reponses(
        db, PRATICIEN, "inclusion", {"inclusion_01": "12", "inclusion_02": "oui"}
    )
    assert ecrites == 2


# --- Mode sans base --------------------------------------------------------


async def test_l_instrumentation_est_inerte_sans_base():
    """En developpement sans base, l'instrumentation ne doit jamais faire
    echouer une generation."""
    assert await ouvrir_session(None, PRATICIEN) is None
    assert await ouvrir_dossier(None, "s", "t", "cr", []) is None
    assert await enregistrer_decision(None, "p", "conforme") is None
    assert await clore_dossier(None, "d", "cr") is None
    assert await enregistrer_reponses(None, PRATICIEN, "inclusion", {"a": "1"}) == 0
