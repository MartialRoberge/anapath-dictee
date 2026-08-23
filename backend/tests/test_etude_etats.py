"""L'etat de decision d'un bloc : ce que l'etude a REELLEMENT mesure.

Ces tests protegent une seule chose, et c'est la plus attaquable de l'etude :
un bloc que le praticien n'a pas touche ne doit jamais etre compte comme
accepte. C'etait une INFERENCE — "il n'a rien dit, donc il etait d'accord" —
et elle recouvre deux situations qui n'ont rien a voir : "j'ai lu et c'est
juste" et "je n'ai jamais vu ce bloc".

Six situations doivent rester distinguables, parce qu'un relecteur d'article
les separera : celui qui VALIDE, celui qui NE VALIDE PAS, celui qui CLIQUE
SANS REGARDER, celui qui S'EN VA au milieu, celui qui PREND DU TEMPS, celui
qui REFUSE. Chacun des tests ci-dessous garde une de ces frontieres.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

import etude.models  # noqa: F401  (enregistre les tables sur Base)
import main
from auth import get_current_user
from database import get_db_session
from db_models import Base, User
from etude.extraction import PropositionExtraite
from etude.models import EtudeDossier, EtudeProposition
from etude.service import (
    abandonner_dossier,
    clore_dossier,
    enregistrer_decision,
    marquer_vue,
    marquer_vues,
    ouvrir_dossier,
    ouvrir_session,
)
from etude.vocabulaire import (
    DECISIONS_PAR_TYPE,
    ETAT_ABANDONNE,
    ETAT_ABSTENU,
    ETAT_ACCEPTE,
    ETAT_CORRIGE,
    ETAT_NON_VU,
    ETAT_REFUSE,
    ETAT_VU_NON_DECIDE,
    ETATS_DECISION,
    ETATS_EXPLICITES,
    ETATS_SANS_DECISION,
    TYPE_CODE,
    TYPE_COMPLETUDE,
    TYPE_RESTITUTION,
    etat_de_la_decision,
)

PRATICIEN = "praticien-etats"
AUTRE = "autre-praticien-etats"

TRANSCRIPTION = (
    "Biopsies etagees du colon sigmoide. Proliferation glandulaire avec "
    "noyaux allonges pseudostratifies, sans franchissement de la musculaire "
    "muqueuse."
)
CR = (
    "**Conclusion :**\n"
    "Adenome tubuleux en dysplasie de bas grade, sans franchissement."
)


# ---------------------------------------------------------------------------
# Le vocabulaire : sept etats, aucune zone grise
# ---------------------------------------------------------------------------


def test_les_etats_se_partagent_en_decides_et_non_decides():
    """Aucun etat ne doit tomber dans les deux moities ni dans aucune : un
    etat non classe rendrait le denominateur des taux de decision arbitraire."""
    assert ETATS_EXPLICITES | ETATS_SANS_DECISION == ETATS_DECISION
    assert not ETATS_EXPLICITES & ETATS_SANS_DECISION


def test_les_trois_absences_de_decision_restent_distinctes():
    """non_vu, vu_non_decide et abandonne ne sont pas interchangeables : le
    bloc n'a pas paru, il a paru et n'a pas ete tranche, ou le praticien est
    parti. Les fondre ferait disparaitre la mesure du parcours."""
    assert len({ETAT_NON_VU, ETAT_VU_NON_DECIDE, ETAT_ABANDONNE}) == 3
    assert ETATS_SANS_DECISION == {ETAT_NON_VU, ETAT_VU_NON_DECIDE, ETAT_ABANDONNE}


def test_chaque_decision_de_chaque_grille_porte_un_etat():
    """La correspondance doit rester TOTALE. Une decision ajoutee plus tard
    sans etat rendrait un bloc DECIDE indistinguable d'un bloc jamais vu, et
    l'erreur ne se verrait qu'au depouillement."""
    for type_proposition, decisions in DECISIONS_PAR_TYPE.items():
        for decision in decisions:
            etat = etat_de_la_decision(type_proposition, decision)
            assert etat in ETATS_EXPLICITES, (
                f"{type_proposition}/{decision} n'a pas d'etat explicite"
            )


def test_je_ne_sais_pas_n_est_pas_un_refus():
    """Un praticien qui dit ne pas savoir n'a pas rejete le code. Le compter
    comme un refus punirait l'honnetete, exactement comme le ferait un taux
    d'exactitude qui le compterait pour une erreur."""
    assert etat_de_la_decision(TYPE_CODE, "je_ne_sais_pas") == ETAT_ABSTENU


def test_une_abstention_reste_une_decision_prise():
    """Elle se distingue de vu_non_decide : le praticien A repondu."""
    assert ETAT_ABSTENU in ETATS_EXPLICITES


def test_pertinent_mais_non_retenu_n_est_pas_un_refus():
    """Juger une suggestion pertinente et choisir de ne pas l'ecrire valide le
    systeme : c'est une decision editoriale sur le compte rendu, pas un rejet.
    La compter comme un refus ferait chuter l'utilite mesuree de la
    completude."""
    assert etat_de_la_decision(TYPE_COMPLETUDE, "pertinent_non_retenu") == ETAT_ACCEPTE
    assert etat_de_la_decision(TYPE_COMPLETUDE, "non_pertinent") == ETAT_REFUSE


def test_une_decision_hors_grille_n_a_pas_d_etat():
    """None et non un etat de repli : ranger d'office une decision inconnue
    fabriquerait une mesure a partir d'une erreur de programmation."""
    assert etat_de_la_decision(TYPE_RESTITUTION, "je_ne_sais_pas") is None
    assert etat_de_la_decision("type_inconnu", "conforme") is None


# ---------------------------------------------------------------------------
# Le service : les transitions d'etat
# ---------------------------------------------------------------------------


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
                email="praticien-etats@marc.test",
                password_hash="x",
                name="Praticien",
            )
        )
        await session.commit()
        yield session
    await moteur.dispose()


def _proposition(
    valeur: str, type_proposition: str = TYPE_RESTITUTION
) -> PropositionExtraite:
    return PropositionExtraite(
        type_proposition=type_proposition,
        sous_type="conclusion",
        valeur_proposee=valeur,
        empan_debut=0,
        empan_fin=10,
        empan_extrait="dictee ici",
        longueur_mots=len(valeur.split()),
    )


async def _dossier_avec(db, propositions: list[PropositionExtraite]) -> EtudeDossier:
    session = await ouvrir_session(db, PRATICIEN)
    assert session is not None
    dossier = await ouvrir_dossier(
        db,
        session_id=session.id,
        transcription=TRANSCRIPTION,
        cr_propose=CR,
        propositions=propositions,
    )
    assert dossier is not None
    return dossier


async def _blocs(db, dossier_id: str) -> list[EtudeProposition]:
    """Lit les blocs du dossier. Requete explicite : pas de lazy-load async."""
    resultat = await db.execute(
        select(EtudeProposition)
        .where(EtudeProposition.dossier_id == dossier_id)
        .order_by(EtudeProposition.id)
    )
    return list(resultat.scalars().all())


# --- Naissance et premier affichage ----------------------------------------


async def test_un_bloc_nait_non_vu(db):
    """Le serveur a REMIS le bloc, il ne l'a pas affiche. Tant que rien ne
    prouve qu'il a paru a l'ecran, l'etude n'a rien mesure sur lui."""
    dossier = await _dossier_avec(db, [_proposition("Adenome tubuleux")])
    bloc = (await _blocs(db, dossier.id))[0]
    assert bloc.etat == ETAT_NON_VU
    assert bloc.vu_a is None


async def test_un_bloc_non_vu_n_est_ni_accepte_ni_refuse(db):
    """LA regle du chantier : un bloc jamais affiche est une ABSENCE DE
    MESURE. Le ranger d'un cote ou de l'autre gonflerait un taux avec des
    blocs que personne n'a lus."""
    dossier = await _dossier_avec(db, [_proposition("Adenome tubuleux")])
    bloc = (await _blocs(db, dossier.id))[0]
    assert bloc.etat not in ETATS_EXPLICITES
    assert bloc.decision is None


async def test_signaler_l_affichage_date_le_bloc_et_change_son_etat(db):
    dossier = await _dossier_avec(db, [_proposition("Adenome tubuleux")])
    bloc = (await _blocs(db, dossier.id))[0]

    vu = await marquer_vue(db, bloc.id)

    assert vu.vu_a is not None
    assert vu.etat == ETAT_VU_NON_DECIDE


async def test_un_second_signalement_n_ecrase_pas_le_premier_affichage(db):
    """IDEMPOTENCE : c'est le PREMIER affichage qui date la mesure. Le
    reecrire ferait repartir de zero le temps de lecture de tout bloc qu'on
    fait defiler deux fois, et le praticien qui relit paraitrait plus
    expeditif que celui qui tranche du premier coup."""
    dossier = await _dossier_avec(db, [_proposition("Adenome tubuleux")])
    bloc = (await _blocs(db, dossier.id))[0]

    premier = (await marquer_vue(db, bloc.id)).vu_a
    second = (await marquer_vue(db, bloc.id)).vu_a

    assert second == premier


# --- Decisions explicites --------------------------------------------------


@pytest.mark.parametrize(
    ("type_proposition", "decision", "attendu"),
    [
        (TYPE_RESTITUTION, "conforme", ETAT_ACCEPTE),
        (TYPE_RESTITUTION, "corrige", ETAT_CORRIGE),
        (TYPE_RESTITUTION, "non_dicte", ETAT_REFUSE),
        (TYPE_RESTITUTION, "hors_sujet", ETAT_REFUSE),
        (TYPE_CODE, "juste", ETAT_ACCEPTE),
        (TYPE_CODE, "je_ne_sais_pas", ETAT_ABSTENU),
        (TYPE_COMPLETUDE, "pertinent_ajoute", ETAT_ACCEPTE),
        (TYPE_COMPLETUDE, "pertinent_non_retenu", ETAT_ACCEPTE),
        (TYPE_COMPLETUDE, "non_pertinent", ETAT_REFUSE),
    ],
)
async def test_une_decision_ecrit_son_etat(db, type_proposition, decision, attendu):
    dossier = await _dossier_avec(db, [_proposition("Adenome", type_proposition)])
    bloc = (await _blocs(db, dossier.id))[0]

    decidee = await enregistrer_decision(db, bloc.id, decision)

    assert decidee.etat == attendu


async def test_une_decision_prouve_l_affichage_sans_fabriquer_sa_date(db):
    """Une decision explicite suffit a dire que le bloc etait sous les yeux du
    praticien. Mais dater son affichage au moment de la decision donnerait
    zero milliseconde de lecture a tout bloc decide sans signal, et ferait
    passer pour expeditif un praticien qu'on n'a simplement pas observe."""
    dossier = await _dossier_avec(db, [_proposition("Adenome tubuleux")])
    bloc = (await _blocs(db, dossier.id))[0]

    decidee = await enregistrer_decision(db, bloc.id, "conforme")

    assert decidee.etat == ETAT_ACCEPTE
    assert decidee.vu_a is None
    assert decidee.latence_vue_ms is None


async def test_un_changement_d_avis_deplace_l_etat(db):
    dossier = await _dossier_avec(db, [_proposition("Adenome tubuleux")])
    bloc = (await _blocs(db, dossier.id))[0]

    await enregistrer_decision(db, bloc.id, "conforme")
    apres = await enregistrer_decision(db, bloc.id, "non_dicte")

    assert apres.etat == ETAT_REFUSE


# --- La latence de lecture -------------------------------------------------


async def test_la_latence_de_lecture_part_de_l_affichage_reel(db):
    """Deux horloges, deux mesures differentes. `latence_ms` court depuis la
    remise du compte rendu entier ; `latence_vue_ms` depuis l'instant ou CE
    bloc a paru. Sur un compte rendu long, la premiere mesure le temps passe
    sur les autres blocs — une latence comptee depuis un affichage qui n'a pas
    eu lieu ne veut rien dire."""
    dossier = await _dossier_avec(db, [_proposition("Adenome tubuleux")])
    bloc = (await _blocs(db, dossier.id))[0]
    # Le compte rendu est a l'ecran depuis une minute ; le bloc, lui, vient
    # tout juste d'apparaitre en defilant.
    bloc.affiche_a = datetime.now(UTC) - timedelta(seconds=60)
    await db.commit()

    await marquer_vue(db, bloc.id)
    decidee = await enregistrer_decision(db, bloc.id, "conforme")

    assert decidee.latence_ms >= 59_000
    assert decidee.latence_vue_ms < 5_000


# --- Abandon ---------------------------------------------------------------


async def test_l_abandon_marque_les_blocs_vus_et_laisses(db):
    """Celui qui s'en va au milieu n'est pas celui qui a fini sans se
    prononcer : le premier a ete interrompu, le second a saute le bloc."""
    dossier = await _dossier_avec(db, [_proposition("Adenome tubuleux")])
    bloc = (await _blocs(db, dossier.id))[0]
    await marquer_vue(db, bloc.id)

    await abandonner_dossier(db, dossier.id, "interruption")

    assert (await _blocs(db, dossier.id))[0].etat == ETAT_ABANDONNE


async def test_l_abandon_laisse_non_vu_un_bloc_jamais_affiche(db):
    """On ne peut pas dire d'un praticien qu'il a quitte un bloc qu'il n'a
    jamais eu sous les yeux. L'ecraser detruirait en plus le compte des blocs
    non vus, qui est justement ce qui distingue un cas survole d'un cas
    interrompu."""
    dossier = await _dossier_avec(
        db, [_proposition("Adenome tubuleux"), _proposition("Limites saines")]
    )
    vu, jamais_vu = await _blocs(db, dossier.id)
    await marquer_vue(db, vu.id)

    await abandonner_dossier(db, dossier.id, "interruption")

    etats = {bloc.id: bloc.etat for bloc in await _blocs(db, dossier.id)}
    assert etats[vu.id] == ETAT_ABANDONNE
    assert etats[jamais_vu.id] == ETAT_NON_VU


async def test_l_abandon_ne_defait_pas_une_decision(db):
    """L'abandon survient APRES : il n'annule pas ce qui a ete tranche."""
    dossier = await _dossier_avec(db, [_proposition("Adenome tubuleux")])
    bloc = (await _blocs(db, dossier.id))[0]
    await enregistrer_decision(db, bloc.id, "conforme")

    await abandonner_dossier(db, dossier.id, "interruption")

    assert (await _blocs(db, dossier.id))[0].etat == ETAT_ACCEPTE


async def test_un_signal_d_affichage_tardif_ne_defait_pas_un_abandon(db):
    """Un lot d'affichages parti juste avant la fermeture de l'onglet ne doit
    pas ramener un bloc abandonne a "vu, non decide" : la mesure du parcours
    serait reecrite par un evenement posterieur au parcours."""
    dossier = await _dossier_avec(db, [_proposition("Adenome tubuleux")])
    bloc = (await _blocs(db, dossier.id))[0]
    await marquer_vue(db, bloc.id)
    await abandonner_dossier(db, dossier.id, "interruption")

    await marquer_vue(db, bloc.id)

    assert (await _blocs(db, dossier.id))[0].etat == ETAT_ABANDONNE


# --- Cloture : le compte des blocs jamais affiches -------------------------


async def test_le_nombre_de_blocs_non_vus_est_nul_avant_la_cloture(db):
    """NUL et non zero : rien n'a encore ete mesure. Ecrire 0 ferait passer
    tout dossier en cours pour un dossier integralement parcouru."""
    dossier = await _dossier_avec(db, [_proposition("Adenome tubuleux")])
    assert (await db.get(EtudeDossier, dossier.id)).nb_blocs_non_vus is None


async def test_la_cloture_compte_les_blocs_jamais_affiches(db):
    """Un compte rendu valide dont la moitie des blocs n'a jamais paru a
    l'ecran ne se lit pas comme un compte rendu entierement revu."""
    dossier = await _dossier_avec(
        db,
        [
            _proposition("Adenome tubuleux"),
            _proposition("Limites saines"),
            _proposition("Pas de dysplasie de haut grade"),
        ],
    )
    blocs = await _blocs(db, dossier.id)
    await marquer_vue(db, blocs[0].id)
    await enregistrer_decision(db, blocs[0].id, "conforme")

    clos = await clore_dossier(db, dossier.id, cr_valide=CR)

    assert clos.nb_blocs_non_vus == 2


async def test_un_bloc_decide_sans_signal_n_est_pas_compte_non_vu(db):
    """La decision prouve l'affichage : le compter non vu contredirait la
    decision que le bloc porte."""
    dossier = await _dossier_avec(db, [_proposition("Adenome tubuleux")])
    bloc = (await _blocs(db, dossier.id))[0]
    await enregistrer_decision(db, bloc.id, "conforme")

    clos = await clore_dossier(db, dossier.id, cr_valide=CR)

    assert clos.nb_blocs_non_vus == 0


async def test_l_abandon_fige_aussi_le_compte_des_blocs_non_vus(db):
    """Un cas interrompu se depouille comme un autre : sans ce compte, on ne
    saurait pas si le praticien est parti apres avoir tout lu ou avant."""
    dossier = await _dossier_avec(
        db, [_proposition("Adenome tubuleux"), _proposition("Limites saines")]
    )
    blocs = await _blocs(db, dossier.id)
    await marquer_vue(db, blocs[0].id)

    await abandonner_dossier(db, dossier.id, "interruption")

    assert (await db.get(EtudeDossier, dossier.id)).nb_blocs_non_vus == 1


# --- Le commentaire libre de validation ------------------------------------


async def test_le_commentaire_de_validation_est_conserve(db):
    """Souvent la seule trace de ce qui a gene le praticien sans qu'aucune
    case ne le capture : une case cochee dit qu'il y a eu un probleme, jamais
    lequel."""
    dossier = await _dossier_avec(db, [])
    clos = await clore_dossier(
        db,
        dossier.id,
        cr_valide=CR,
        commentaire_validation="  La segmentation en deux prelevements m'a gene.  ",
    )
    assert clos.commentaire_validation == (
        "La segmentation en deux prelevements m'a gene."
    )


async def test_un_commentaire_vide_reste_nul(db):
    """Une chaine vide et une absence de commentaire se lisent pareil mais se
    COMPTENT differemment : sans normalisation, le nombre de cas commentes
    compterait chaque champ laisse vide."""
    dossier = await _dossier_avec(db, [])
    clos = await clore_dossier(db, dossier.id, cr_valide=CR, commentaire_validation="   ")
    assert clos.commentaire_validation is None


# --- Envoi groupe ----------------------------------------------------------


async def test_un_envoi_groupe_date_tous_les_blocs_du_dossier(db):
    dossier = await _dossier_avec(
        db, [_proposition("Adenome tubuleux"), _proposition("Limites saines")]
    )
    blocs = await _blocs(db, dossier.id)

    marquees, ignorees = await marquer_vues(db, dossier.id, [b.id for b in blocs])

    assert (marquees, ignorees) == (2, 0)
    assert all(b.etat == ETAT_VU_NON_DECIDE for b in await _blocs(db, dossier.id))


async def test_un_envoi_groupe_ne_compte_pas_deux_fois_le_meme_bloc(db):
    """Il n'y a qu'un premier affichage par bloc : un lot rejoue ne doit rien
    ajouter au compte, sans quoi le nombre de blocs vus depasserait le nombre
    de blocs."""
    dossier = await _dossier_avec(db, [_proposition("Adenome tubuleux")])
    bloc = (await _blocs(db, dossier.id))[0]

    premier, _ = await marquer_vues(db, dossier.id, [bloc.id])
    second, _ = await marquer_vues(db, dossier.id, [bloc.id])

    assert (premier, second) == (1, 0)


async def test_un_envoi_groupe_compte_les_identifiants_etrangers(db):
    """Les refuser en bloc ferait perdre les signaux valides du meme lot ; les
    taire cacherait un defaut du client."""
    dossier = await _dossier_avec(db, [_proposition("Adenome tubuleux")])
    bloc = (await _blocs(db, dossier.id))[0]

    marquees, ignorees = await marquer_vues(
        db, dossier.id, [bloc.id, "bloc-d-un-autre-dossier"]
    )

    assert (marquees, ignorees) == (1, 1)


# --- Mode sans base --------------------------------------------------------


async def test_le_suivi_des_etats_est_inerte_sans_base():
    """En developpement sans base, l'instrumentation ne doit jamais faire
    echouer une generation."""
    assert await marquer_vue(None, "proposition") is None
    assert await marquer_vues(None, "dossier", ["proposition"]) == (0, 0)


# ---------------------------------------------------------------------------
# Les routes
# ---------------------------------------------------------------------------


def _utilisateur(identifiant: str) -> User:
    user = User()
    user.id = identifiant
    user.email = f"{identifiant}@marc.test"
    user.name = "Praticien"
    user.role = "user"
    return user


@pytest.fixture
def client(tmp_path):
    """Client API branche sur une base SQLite de fichier, jetable.

    Un fichier plutot que :memory: — chaque connexion a une base en memoire
    ouvre sa PROPRE base, et les ecritures d'une requete seraient invisibles a
    la suivante.
    """
    moteur = create_async_engine(
        f"sqlite+aiosqlite:///{tmp_path / 'etats.db'}", poolclass=NullPool
    )
    fabrique = async_sessionmaker(moteur, expire_on_commit=False)

    async def _base():
        async with fabrique() as session:
            yield session

    app = main.app
    app.dependency_overrides[get_db_session] = _base
    app.dependency_overrides[get_current_user] = lambda: _utilisateur(PRATICIEN)

    with TestClient(app) as c:
        c.portal.call(_creer_schema, moteur)
        yield c
        app.dependency_overrides.clear()
        c.portal.call(moteur.dispose)


async def _creer_schema(moteur) -> None:
    async with moteur.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    fabrique = async_sessionmaker(moteur, expire_on_commit=False)
    async with fabrique() as session:
        for identifiant in (PRATICIEN, AUTRE):
            session.add(
                User(
                    id=identifiant,
                    email=f"{identifiant}@marc.test",
                    password_hash="x",
                    name="Praticien",
                )
            )
        await session.commit()


def _ouvrir_dossier(client) -> dict:
    session_id = client.post("/etude/sessions").json()["session_id"]
    reponse = client.post(
        "/etude/dossiers",
        json={
            "session_id": session_id,
            "transcription": TRANSCRIPTION,
            "cr_propose": CR,
            "organe": "colon",
        },
    )
    assert reponse.status_code == 201, reponse.text
    return reponse.json()


def test_la_route_d_affichage_est_idempotente(client):
    """Rappelee sur un bloc deja date, elle ne change rien : c'est le premier
    affichage qui date la mesure."""
    dossier = _ouvrir_dossier(client)
    bloc = dossier["propositions"][0]

    premier = client.post(f"/etude/propositions/{bloc['id']}/vue")
    second = client.post(f"/etude/propositions/{bloc['id']}/vue")

    assert premier.status_code == 200
    assert second.status_code == 200
    assert second.json()["vu_a"] == premier.json()["vu_a"]
    assert second.json()["etat"] == "vu_non_decide"


def test_un_praticien_ne_signale_pas_l_affichage_d_un_autre(client):
    """Sans ce cloisonnement, un identifiant devine suffirait a declarer lu un
    bloc que le confrere n'a jamais vu."""
    dossier = _ouvrir_dossier(client)
    bloc = dossier["propositions"][0]

    main.app.dependency_overrides[get_current_user] = lambda: _utilisateur(AUTRE)
    reponse = client.post(f"/etude/propositions/{bloc['id']}/vue")

    assert reponse.status_code == 403


def test_la_route_de_decision_rend_l_etat(client):
    """L'interface doit pouvoir montrer au praticien ou en est chaque bloc :
    c'est cette relecture qui rend les etats verifiables par l'utilisateur."""
    dossier = _ouvrir_dossier(client)
    bloc = dossier["propositions"][0]
    client.post(f"/etude/propositions/{bloc['id']}/vue")

    reponse = client.post(
        f"/etude/propositions/{bloc['id']}/decision", json={"decision": "conforme"}
    )

    assert reponse.status_code == 200
    corps = reponse.json()
    assert corps["etat"] == ETAT_ACCEPTE
    assert corps["latence_vue_ms"] is not None


def test_l_envoi_groupe_compte_ce_qu_il_a_date_et_ce_qu_il_ignore(client):
    dossier = _ouvrir_dossier(client)
    identifiants = [bloc["id"] for bloc in dossier["propositions"]]

    reponse = client.post(
        f"/etude/dossiers/{dossier['dossier_id']}/vues",
        json={"propositions": [*identifiants, "identifiant-etranger"]},
    )

    assert reponse.status_code == 200
    assert reponse.json() == {"marquees": len(identifiants), "ignorees": 1}


def test_la_cloture_annonce_les_blocs_jamais_affiches(client):
    """Le chiffre revient au client pour que l'interface puisse le dire au
    praticien AVANT qu'il ne signe."""
    dossier = _ouvrir_dossier(client)
    assert dossier["propositions"], "aucune proposition extraite du CR de test"

    reponse = client.post(
        f"/etude/dossiers/{dossier['dossier_id']}/cloture",
        json={"cr_valide": CR, "commentaire_validation": "Rien a signaler."},
    )

    assert reponse.status_code == 200
    assert reponse.json()["blocs_non_vus"] == len(dossier["propositions"])
