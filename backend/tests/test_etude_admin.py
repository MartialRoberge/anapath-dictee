"""Vues d'administration de l'etude : le macro et le micro.

Le micro est ce qui rend l'etude defendable : un taux surprenant ne se corrige
pas, il s'explique. Ces tests verifient qu'on peut vraiment remonter d'un
chiffre agrege jusqu'a la phrase de dictee qui l'a produit.
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

PRATICIEN = "praticien-admin-test"

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


def _user(identifiant: str, role: str) -> User:
    user = User()
    user.id = identifiant
    user.email = f"{identifiant}@marc.test"
    user.name = "Compte"
    user.role = role
    return user


async def _creer_schema(moteur) -> None:
    import etude.models  # noqa: F401  (enregistre les tables sur Base)

    async with moteur.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    fabrique = async_sessionmaker(moteur, expire_on_commit=False)
    async with fabrique() as session:
        session.add(
            User(
                id=PRATICIEN,
                email="p@marc.test",
                password_hash="x",
                name="Praticien",
                role="user",
            )
        )
        await session.commit()


@pytest.fixture
def client(tmp_path):
    moteur = create_async_engine(
        f"sqlite+aiosqlite:///{tmp_path / 'admin.db'}", poolclass=NullPool
    )
    fabrique = async_sessionmaker(moteur, expire_on_commit=False)

    async def _base():
        async with fabrique() as session:
            yield session

    app = main.app
    app.dependency_overrides[get_db_session] = _base
    app.dependency_overrides[get_current_user] = lambda: _user(PRATICIEN, "user")

    with TestClient(app) as c:
        c.portal.call(_creer_schema, moteur)
        yield c
        app.dependency_overrides.clear()
        c.portal.call(moteur.dispose)


def _passer_admin() -> None:
    main.app.dependency_overrides[get_current_user] = lambda: _user("adm", "admin")


def _jouer_un_cas(client) -> dict:
    """Deroule un cas complet en tant que praticien."""
    session_id = client.post("/etude/sessions").json()["session_id"]
    dossier = client.post(
        "/etude/dossiers",
        json={
            "session_id": session_id,
            "transcription": TRANSCRIPTION,
            "cr_propose": CR,
            "organe": "colon",
        },
    ).json()
    for proposition in dossier["propositions"]:
        client.post(
            f"/etude/propositions/{proposition['id']}/decision",
            json={"decision": "conforme"},
        )
    client.post(
        f"/etude/dossiers/{dossier['dossier_id']}/cloture",
        json={"cr_valide": CR + " Ajout du relecteur.", "omission_signalee": False},
    )
    return dossier


# --- Acces ------------------------------------------------------------------


def test_un_praticien_ne_voit_pas_la_synthese(client):
    """Les taux agreges de tous les confreres ne regardent pas un participant."""
    assert client.get("/admin/etude/synthese").status_code == 403


# --- Macro ------------------------------------------------------------------


def test_la_synthese_expose_les_denominateurs(client):
    """Un taux sans son denominateur n'est pas un resultat : le lecteur doit
    pouvoir refaire le calcul."""
    _jouer_un_cas(client)
    _passer_admin()

    synthese = client.get("/admin/etude/synthese").json()
    taux = synthese["propositions"]["toutes_decisions"]["taux"]
    for indicateur in taux.values():
        assert "numerateur" in indicateur
        assert "denominateur" in indicateur


def test_la_synthese_est_calculee_avec_et_sans_les_hatives(client):
    """L'ecart entre les deux lectures mesure combien le verrou d'export a
    gonfle les resultats."""
    _jouer_un_cas(client)
    _passer_admin()
    synthese = client.get("/admin/etude/synthese").json()["propositions"]
    assert "toutes_decisions" in synthese
    assert "hors_decisions_hatives" in synthese


def test_la_synthese_decrit_le_corpus(client):
    _jouer_un_cas(client)
    _passer_admin()
    corpus = client.get("/admin/etude/synthese").json()["corpus"]
    assert corpus["nb_praticiens"] == 1
    assert corpus["nb_dossiers"] == 1
    assert corpus["nb_dossiers_clos"] == 1
    assert corpus["organes"] == {"colon": 1}


def test_la_liste_des_dossiers_donne_l_avancement(client):
    _jouer_un_cas(client)
    _passer_admin()
    lignes = client.get("/admin/etude/dossiers").json()
    assert len(lignes) == 1
    assert lignes[0]["nb_decidees"] == lignes[0]["nb_propositions"]
    assert lignes[0]["caracteres_modifies"] > 0


def test_une_etude_vide_ne_fabrique_pas_de_taux(client):
    """Zero pour cent la ou l'on n'a rien observe est la maniere la plus
    courante de mentir avec un tableau."""
    _passer_admin()
    synthese = client.get("/admin/etude/synthese").json()
    taux = synthese["propositions"]["toutes_decisions"]["taux"]
    assert taux["acceptation_sans_modification"]["valeur"] is None
    assert synthese["corpus"]["nb_dossiers"] == 0


# --- Micro ------------------------------------------------------------------


def test_le_micro_restitue_les_deux_versions_du_compte_rendu(client):
    """Sans le texte propose a cote du texte valide, la charge d'edition n'est
    pas verifiable a la main."""
    dossier = _jouer_un_cas(client)
    _passer_admin()
    detail = client.get(f"/admin/etude/dossiers/{dossier['dossier_id']}").json()
    assert detail["cr_propose"] == CR
    assert detail["cr_valide"].endswith("Ajout du relecteur.")
    assert detail["transcription"] == TRANSCRIPTION


def test_le_micro_donne_le_passage_de_dictee_de_chaque_proposition(client):
    """L'administrateur ne doit pas avoir a refaire un calcul d'offsets pour
    relire un cas : c'est ce qui transforme une anomalie en explication."""
    dossier = _jouer_un_cas(client)
    _passer_admin()
    detail = client.get(f"/admin/etude/dossiers/{dossier['dossier_id']}").json()

    restitutions = [p for p in detail["propositions"] if p["type"] == "restitution"]
    assert restitutions, "aucune restitution extraite du CR de test"
    for proposition in restitutions:
        assert proposition["empan_extrait"]
        assert proposition["empan_extrait"] in TRANSCRIPTION
        assert proposition["decision"] == "conforme"
        assert proposition["latence_ms"] is not None


def test_le_micro_donne_les_temps(client):
    dossier = _jouer_un_cas(client)
    _passer_admin()
    temps = client.get(f"/admin/etude/dossiers/{dossier['dossier_id']}").json()["temps"]
    assert temps["revision_ms"] is not None
    assert temps["revision_nette_ms"] is not None
    assert temps["nb_pauses"] == 0


def test_un_dossier_inconnu_sort_en_404(client):
    _passer_admin()
    assert client.get("/admin/etude/dossiers/inexistant").status_code == 404


# --- Exclusion : ecarter sans detruire --------------------------------------


def test_un_dossier_exclu_ne_compte_dans_aucun_taux(client):
    """L'administrateur teste l'outil sans etre pathologiste, et des saisies
    aberrantes arrivent. Une exclusion qui n'exclut pas serait pire qu'aucune :
    elle donnerait l'illusion d'un corpus propre."""
    dossier = _jouer_un_cas(client)
    _passer_admin()

    avant = client.get("/admin/etude/synthese").json()
    assert avant["corpus"]["nb_dossiers"] == 1
    assert avant["propositions"]["toutes_decisions"]["decidees"] > 0

    client.post(
        f"/admin/etude/dossiers/{dossier['dossier_id']}/exclusion",
        json={"motif": "Essai de l'administrateur, pas un cas reel"},
    )

    apres = client.get("/admin/etude/synthese").json()
    assert apres["corpus"]["nb_dossiers"] == 0
    assert apres["propositions"]["toutes_decisions"]["decidees"] == 0


def test_le_nombre_d_exclus_est_toujours_affiche(client):
    """Une publication doit dire combien de cas ont ete ecartes : les cacher
    rendrait l'effectif incomprehensible."""
    dossier = _jouer_un_cas(client)
    _passer_admin()
    client.post(
        f"/admin/etude/dossiers/{dossier['dossier_id']}/exclusion",
        json={"motif": "Essai"},
    )
    corpus = client.get("/admin/etude/synthese").json()["corpus"]
    assert corpus["nb_exclus"] == 1


def test_une_exclusion_se_defait(client):
    """On ecarte un cas par erreur bien plus souvent qu'on ne veut le detruire."""
    dossier = _jouer_un_cas(client)
    _passer_admin()
    url = f"/admin/etude/dossiers/{dossier['dossier_id']}/exclusion"
    client.post(url, json={"motif": "Essai"})
    reponse = client.post(url, json={"motif": "", "exclu": False})
    assert reponse.status_code == 200
    assert reponse.json()["exclu"] is False
    assert client.get("/admin/etude/synthese").json()["corpus"]["nb_dossiers"] == 1


def test_une_exclusion_sans_motif_est_refusee(client):
    """Un motif vide rendrait l'exclusion inexplicable au depouillement, donc
    inutilisable dans une publication."""
    dossier = _jouer_un_cas(client)
    _passer_admin()
    reponse = client.post(
        f"/admin/etude/dossiers/{dossier['dossier_id']}/exclusion",
        json={"motif": "   "},
    )
    assert reponse.status_code == 400


def test_le_dossier_exclu_reste_consultable(client):
    """Ecarte n'est pas detruit : on doit pouvoir le relire pour verifier que
    l'exclusion etait justifiee."""
    dossier = _jouer_un_cas(client)
    _passer_admin()
    client.post(
        f"/admin/etude/dossiers/{dossier['dossier_id']}/exclusion",
        json={"motif": "Essai"},
    )
    detail = client.get(f"/admin/etude/dossiers/{dossier['dossier_id']}")
    assert detail.status_code == 200
    assert detail.json()["transcription"] == TRANSCRIPTION

    lignes = client.get("/admin/etude/dossiers").json()
    assert lignes[0]["exclu"] is True
    assert lignes[0]["motif_exclusion"] == "Essai"
