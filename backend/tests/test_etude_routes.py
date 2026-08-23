"""Routes de l'instrumentation, de bout en bout.

Ces tests verifient ce que les tests de service ne peuvent pas voir : qu'un
refus d'etude sort en 400 et pas en 500, qu'un praticien ne peut pas decider a
la place d'un autre, et qu'une base absente est refusee bruyamment plutot que
de perdre une mesure en silence.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

import main
from auth import get_current_user
from database import get_db_session
from db_models import Base, User

PRATICIEN = "praticien-routes"
AUTRE = "autre-praticien"

TRANSCRIPTION = (
    "Biopsies etagees du colon sigmoide. A l'histologie, proliferation "
    "glandulaire avec noyaux allonges pseudostratifies limites a la moitie "
    "basale de l'epithelium, sans franchissement de la musculaire muqueuse."
)
CR = (
    "**Conclusion :**\n"
    "Adenome tubuleux en dysplasie de bas grade, respectant la musculaire "
    "muqueuse du sigmoide, sans franchissement."
)


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
        f"sqlite+aiosqlite:///{tmp_path / 'etude.db'}", poolclass=NullPool
    )
    fabrique = async_sessionmaker(moteur, expire_on_commit=False)

    async def _base():
        async with fabrique() as session:
            yield session

    app = main.app
    app.dependency_overrides[get_db_session] = _base
    app.dependency_overrides[get_current_user] = lambda: _utilisateur(PRATICIEN)

    with TestClient(app) as c:
        # Le portal du client est le seul point d'entree vers sa boucle async ;
        # il disparait a la sortie du bloc, donc tout le cycle de vie du moteur
        # doit tenir a l'interieur.
        c.portal.call(_creer_schema, moteur)
        yield c
        app.dependency_overrides.clear()
        c.portal.call(moteur.dispose)


async def _creer_schema(moteur) -> None:
    import etude.models  # noqa: F401  (enregistre les tables sur Base)

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


# --- Parcours nominal ------------------------------------------------------


def test_le_parcours_complet_enregistre_la_mesure(client):
    dossier = _ouvrir_dossier(client)
    assert dossier["propositions"], "aucune proposition extraite du CR de test"

    proposition = dossier["propositions"][0]
    decision = client.post(
        f"/etude/propositions/{proposition['id']}/decision",
        json={"decision": "conforme"},
    )
    assert decision.status_code == 200
    assert decision.json()["latence_ms"] >= 0

    cloture = client.post(
        f"/etude/dossiers/{dossier['dossier_id']}/cloture",
        json={"cr_valide": CR, "omission_signalee": False},
    )
    assert cloture.status_code == 200
    assert cloture.json()["caracteres_modifies"] == 0

    assert client.post(f"/etude/dossiers/{dossier['dossier_id']}/export").status_code == 200


def test_chaque_proposition_affichee_porte_son_empan(client):
    """Regle fondatrice : pas d'empan, pas de proposition. Une proposition
    sans empan ne doit meme pas atteindre le client."""
    dossier = _ouvrir_dossier(client)
    for proposition in dossier["propositions"]:
        if proposition["type"] == "completude":
            continue  # une completude constate une absence, elle n'affirme rien
        assert proposition["empan_fin"] > proposition["empan_debut"]


# --- Refus d'etude : 400, pas 500 -----------------------------------------


def test_une_decision_hors_grille_sort_en_400(client):
    """Un refus d'etude est une erreur de l'appelant, pas une panne serveur."""
    dossier = _ouvrir_dossier(client)
    proposition = dossier["propositions"][0]
    reponse = client.post(
        f"/etude/propositions/{proposition['id']}/decision",
        json={"decision": "je_ne_sais_pas"},
    )
    assert reponse.status_code == 400
    assert "grille" in reponse.json()["detail"]


def test_un_motif_d_abandon_inconnu_sort_en_400(client):
    dossier = _ouvrir_dossier(client)
    reponse = client.post(
        f"/etude/dossiers/{dossier['dossier_id']}/abandon", json={"motif": "flemme"}
    )
    assert reponse.status_code == 400


def test_un_questionnaire_inconnu_sort_en_400(client):
    reponse = client.post(
        "/etude/questionnaires",
        json={"questionnaire": "sus_maison", "reponses": {"a": "1"}},
    )
    assert reponse.status_code == 400


# --- Cloisonnement entre praticiens ---------------------------------------


def test_un_praticien_ne_decide_pas_a_la_place_d_un_autre(client):
    """Sans ce cloisonnement, un identifiant devine suffirait a polluer la
    mesure d'un confrere."""
    dossier = _ouvrir_dossier(client)
    proposition = dossier["propositions"][0]

    main.app.dependency_overrides[get_current_user] = lambda: _utilisateur(AUTRE)
    reponse = client.post(
        f"/etude/propositions/{proposition['id']}/decision",
        json={"decision": "conforme"},
    )
    assert reponse.status_code == 403


def test_un_dossier_inconnu_sort_en_404(client):
    reponse = client.post(
        "/etude/dossiers/inexistant/cloture", json={"cr_valide": "x"}
    )
    assert reponse.status_code == 404


def test_une_session_d_un_autre_praticien_est_refusee(client):
    session_id = client.post("/etude/sessions").json()["session_id"]
    main.app.dependency_overrides[get_current_user] = lambda: _utilisateur(AUTRE)
    reponse = client.post(
        "/etude/dossiers",
        json={
            "session_id": session_id,
            "transcription": TRANSCRIPTION,
            "cr_propose": CR,
        },
    )
    assert reponse.status_code == 404


# --- Abandon ---------------------------------------------------------------


def test_un_dossier_abandonne_ne_se_clot_plus(client):
    dossier = _ouvrir_dossier(client)
    assert client.post(
        f"/etude/dossiers/{dossier['dossier_id']}/abandon",
        json={"motif": "outil_trop_lent"},
    ).status_code == 200
    reponse = client.post(
        f"/etude/dossiers/{dossier['dossier_id']}/cloture", json={"cr_valide": CR}
    )
    assert reponse.status_code == 400


# --- Questionnaires --------------------------------------------------------


def test_le_questionnaire_par_cas_est_servi_par_le_backend(client):
    """Les libelles viennent du backend : un libelle recopie dans un composant
    React derive au premier remaniement, et le depouillement ne s'y retrouve
    plus des mois apres."""
    reponse = client.get("/etude/questionnaires/par_cas")
    assert reponse.status_code == 200
    items = reponse.json()["items"]
    assert any(item["id"] == "par_cas_04" for item in items)


def test_le_questionnaire_de_fin_est_bloque_tant_que_le_fsus_n_est_pas_recopie(client):
    """Servir un F-SUS sans ses libelles publies produirait un score qui ne se
    compare a rien : mieux vaut bloquer que recolter de l'inexploitable."""
    reponse = client.get("/etude/questionnaires/fin_etude")
    assert reponse.status_code == 409
    assert "Gronier" in reponse.json()["detail"]


def test_un_questionnaire_inexistant_sort_en_404(client):
    assert client.get("/etude/questionnaires/inconnu").status_code == 404
