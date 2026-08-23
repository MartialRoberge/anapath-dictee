"""Mesure d'ergonomie : ce qu'elle compte, et ce qu'elle refuse de compter.

Deux familles de tests. Les premieres portent sur la regle de lecture de la
table — un instantane cumule ne se somme pas — parce que s'y tromper gonflerait
les temps d'usage proportionnellement au nombre d'envois, c'est-a-dire a la
duree de la session : le biais grandirait avec la mesure elle-meme.

Les secondes portent sur les trois regles de l'etude : un taux montre son
denominateur, une absence de mesure n'est pas un zero, et un dossier exclu
n'entre dans aucun calcul.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

import main
from auth import get_current_user
from database import get_db_session
from db_models import Base, User
from etude.ergonomie import (
    ZONE_ANALYSE,
    ZONE_BARRE_AJOUT,
    ZONE_COMPTE_RENDU,
    ZONES,
    ReleveObserve,
    agreger,
    dernier_par_zone,
    zone_valide,
)

PRATICIEN = "praticien-ergo-test"
AUTRE = "autre-praticien-ergo"

TRANSCRIPTION = (
    "Biopsie gastrique antrale. Muqueuse fundique avec infiltrat inflammatoire "
    "lymphoplasmocytaire moderee du chorion, sans atrophie glandulaire."
)
CR = "**Conclusion :**\nGastrite chronique moderee, sans atrophie."

DEPART = datetime(2026, 9, 15, 9, 0, 0)


def _releve(
    dossier: str,
    zone: str,
    *,
    visible_ms: int = 0,
    clics: int = 0,
    profondeur_max: float | None = None,
    rang: int | None = None,
    part_largeur: float | None = None,
    minutes: int = 0,
) -> ReleveObserve:
    return ReleveObserve(
        dossier_id=dossier,
        zone=zone,
        visible_ms=visible_ms,
        clics=clics,
        profondeur_max=profondeur_max,
        rang_premiere_visite=rang,
        part_largeur=part_largeur,
        releve_a=DEPART + timedelta(minutes=minutes),
    )


def _profil(agrege: dict[str, object], zone: str) -> dict[str, object]:
    """Le profil d'une zone dans la sortie agregee."""
    zones = agrege["zones"]
    assert isinstance(zones, list)
    return next(profil for profil in zones if profil["zone"] == zone)


# ---------------------------------------------------------------------------
# La regle de lecture : un instantane cumule ne se somme pas
# ---------------------------------------------------------------------------


def test_seul_le_dernier_instantane_de_chaque_zone_compte():
    """Les compteurs sont cumules depuis l'ouverture du dossier. Les sommer
    compterait les memes secondes autant de fois qu'il y a eu d'envois."""
    releves = [
        _releve("d1", ZONE_ANALYSE, visible_ms=10_000, clics=2, minutes=0),
        _releve("d1", ZONE_ANALYSE, visible_ms=25_000, clics=5, minutes=1),
        _releve("d1", ZONE_ANALYSE, visible_ms=40_000, clics=9, minutes=2),
    ]
    retenus = dernier_par_zone(releves)

    assert len(retenus) == 1
    assert retenus[("d1", ZONE_ANALYSE)].visible_ms == 40_000
    profil = _profil(agreger(releves), ZONE_ANALYSE)
    assert profil["temps_visible_ms_moyen"] == 40_000
    assert profil["clics_moyens"] == 9


def test_un_lot_perdu_ne_coute_que_du_detail():
    """Le premier lot manque a l'appel : le total reste juste, seul le decoupage
    dans le temps est perdu. C'est tout l'interet de l'instantane."""
    complet = agreger(
        [
            _releve("d1", ZONE_ANALYSE, visible_ms=10_000, minutes=0),
            _releve("d1", ZONE_ANALYSE, visible_ms=40_000, minutes=2),
        ]
    )
    ampute = agreger([_releve("d1", ZONE_ANALYSE, visible_ms=40_000, minutes=2)])

    assert _profil(complet, ZONE_ANALYSE) == _profil(ampute, ZONE_ANALYSE)


def test_deux_lots_dans_la_meme_seconde_se_departagent_sur_le_cumul():
    """SQLite date a la seconde. Sans regle de depart, l'ordre des lignes rendues
    par la base deciderait, et un instantane ancien pourrait effacer un plus
    complet — le temps d'usage se mettrait a dependre du plan de requete."""
    retenus = dernier_par_zone(
        [
            _releve("d1", ZONE_ANALYSE, visible_ms=30_000, clics=6, minutes=1),
            _releve("d1", ZONE_ANALYSE, visible_ms=12_000, clics=2, minutes=1),
        ]
    )

    assert retenus[("d1", ZONE_ANALYSE)].visible_ms == 30_000


def test_chaque_zone_garde_son_propre_dernier_instantane():
    releves = [
        _releve("d1", ZONE_ANALYSE, visible_ms=30_000, minutes=1),
        _releve("d1", ZONE_COMPTE_RENDU, visible_ms=90_000, minutes=1),
        _releve("d1", ZONE_ANALYSE, visible_ms=35_000, minutes=2),
    ]
    agrege = agreger(releves)

    assert _profil(agrege, ZONE_ANALYSE)["temps_visible_ms_moyen"] == 35_000
    assert _profil(agrege, ZONE_COMPTE_RENDU)["temps_visible_ms_moyen"] == 90_000
    assert agrege["nb_dossiers_mesures"] == 1


# ---------------------------------------------------------------------------
# Une absence de mesure n'est pas un zero
# ---------------------------------------------------------------------------


def test_sans_aucun_releve_rien_n_est_fabrique():
    """Zero pour cent la ou l'on n'a rien observe est la maniere la plus
    courante de mentir avec un tableau."""
    agrege = agreger([])

    assert agrege["nb_dossiers_mesures"] == 0
    for zone in ZONES:
        profil = _profil(agrege, zone)
        assert profil["temps_visible_ms_moyen"] is None
        assert profil["clics_moyens"] is None
        assert profil["profondeur_moyenne"] is None
        assert profil["part_largeur_moyenne"] is None
        assert profil["premiere_visite"]["valeur"] is None


def test_une_zone_qui_tient_dans_l_ecran_n_a_pas_de_profondeur():
    """Pas de defilement possible, pas de profondeur : ecrire 100 % confondrait
    « il a tout parcouru » et « il n'y avait rien a parcourir »."""
    profil = _profil(
        agreger(
            [
                _releve("d1", ZONE_ANALYSE, visible_ms=1_000, profondeur_max=None),
                _releve("d2", ZONE_ANALYSE, visible_ms=1_000, profondeur_max=0.5),
            ]
        ),
        ZONE_ANALYSE,
    )

    # La moyenne porte sur la seule zone ou une profondeur etait mesurable.
    assert profil["profondeur_moyenne"] == 0.5
    assert profil["nb_dossiers_profondeur"] == 1
    assert profil["nb_dossiers"] == 2


def test_le_partage_de_largeur_a_son_propre_denominateur():
    """Une zone qui ne partage pas l'ecran n'a pas de partage a montrer."""
    profil = _profil(
        agreger(
            [
                _releve("d1", ZONE_ANALYSE, part_largeur=0.4),
                _releve("d2", ZONE_ANALYSE, part_largeur=0.6),
                _releve("d3", ZONE_ANALYSE, part_largeur=None),
            ]
        ),
        ZONE_ANALYSE,
    )

    assert profil["part_largeur_moyenne"] == 0.5
    assert profil["nb_dossiers_largeur"] == 2
    assert profil["nb_dossiers"] == 3


# ---------------------------------------------------------------------------
# Par ou commence-t-on ?
# ---------------------------------------------------------------------------


def test_l_ordre_de_depart_montre_son_denominateur():
    """Deux dossiers commencent par l'analyse, un par le compte rendu : les
    parts se lisent sur les trois dossiers ou un depart a ete observe."""
    agrege = agreger(
        [
            _releve("d1", ZONE_ANALYSE, rang=1),
            _releve("d1", ZONE_COMPTE_RENDU, rang=2),
            _releve("d2", ZONE_ANALYSE, rang=1),
            _releve("d3", ZONE_COMPTE_RENDU, rang=1),
            _releve("d3", ZONE_ANALYSE, rang=2),
        ]
    )

    depart_analyse = _profil(agrege, ZONE_ANALYSE)["premiere_visite"]
    assert depart_analyse["numerateur"] == 2
    assert depart_analyse["denominateur"] == 3
    assert agrege["ordre_de_depart"] == {ZONE_ANALYSE: 2, ZONE_COMPTE_RENDU: 1}


def test_un_dossier_sans_geste_date_ne_pese_pas_sur_l_ordre_de_depart():
    """L'inclure au denominateur ferait baisser toutes les parts sans qu'aucune
    observation ne le justifie."""
    agrege = agreger(
        [
            _releve("d1", ZONE_ANALYSE, rang=1),
            _releve("d2", ZONE_ANALYSE, visible_ms=5_000, rang=None),
        ]
    )

    assert agrege["nb_dossiers_mesures"] == 2
    assert agrege["nb_dossiers_commences"] == 1
    assert _profil(agrege, ZONE_ANALYSE)["premiere_visite"]["denominateur"] == 1


def test_le_vocabulaire_des_zones_est_ferme():
    assert zone_valide(ZONE_BARRE_AJOUT)
    assert not zone_valide("panneau-de-gauche")


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


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


@pytest.fixture
def client(tmp_path):
    moteur = create_async_engine(
        f"sqlite+aiosqlite:///{tmp_path / 'ergonomie.db'}", poolclass=NullPool
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


def _passer(identifiant: str, role: str) -> None:
    main.app.dependency_overrides[get_current_user] = lambda: _user(identifiant, role)


def _ouvrir_un_dossier(client) -> str:
    session_id = client.post("/etude/sessions").json()["session_id"]
    return client.post(
        "/etude/dossiers",
        json={
            "session_id": session_id,
            "transcription": TRANSCRIPTION,
            "cr_propose": CR,
            "organe": "estomac",
        },
    ).json()["dossier_id"]


def _deposer(client, dossier_id: str, releves: list[dict[str, object]]):
    return client.post(
        f"/etude/dossiers/{dossier_id}/ergonomie", json={"releves": releves}
    )


def test_un_lot_se_depose_et_se_relit_agrege(client):
    dossier_id = _ouvrir_un_dossier(client)
    reponse = _deposer(
        client,
        dossier_id,
        [
            {
                "zone": ZONE_ANALYSE,
                "visible_ms": 42_000,
                "clics": 7,
                "profondeur_max": 0.8,
                "rang_premiere_visite": 1,
                "part_largeur": 0.38,
            },
            {"zone": ZONE_COMPTE_RENDU, "visible_ms": 61_000, "clics": 3},
        ],
    )
    assert reponse.status_code == 200
    assert reponse.json()["releves_enregistres"] == 2

    _passer("adm", "admin")
    agrege = client.get("/admin/etude/ergonomie").json()
    analyse = _profil(agrege, ZONE_ANALYSE)
    assert analyse["temps_visible_ms_moyen"] == 42_000
    assert analyse["clics_moyens"] == 7
    assert analyse["profondeur_moyenne"] == 0.8
    assert analyse["part_largeur_moyenne"] == 0.38
    assert agrege["ordre_de_depart"] == {ZONE_ANALYSE: 1}


def test_deux_lots_du_meme_dossier_ne_cumulent_pas_le_temps(client):
    """Le client renvoie ses compteurs entiers : le serveur ne doit pas les
    additionner, sinon le temps d'usage grandirait avec le nombre d'envois."""
    dossier_id = _ouvrir_un_dossier(client)
    _deposer(client, dossier_id, [{"zone": ZONE_ANALYSE, "visible_ms": 15_000}])
    _deposer(client, dossier_id, [{"zone": ZONE_ANALYSE, "visible_ms": 30_000}])

    _passer("adm", "admin")
    agrege = client.get("/admin/etude/ergonomie").json()
    assert _profil(agrege, ZONE_ANALYSE)["temps_visible_ms_moyen"] == 30_000
    assert agrege["nb_dossiers_mesures"] == 1


def test_une_zone_inconnue_fait_refuser_le_lot_entier(client):
    """Ecarter la zone en silence donnerait, au depouillement, un panneau que
    personne n'a visite : on lirait un resultat la ou il n'y a qu'un cablage
    fautif."""
    dossier_id = _ouvrir_un_dossier(client)
    reponse = _deposer(
        client,
        dossier_id,
        [
            {"zone": ZONE_ANALYSE, "visible_ms": 9_000},
            {"zone": "sidebar", "visible_ms": 9_000},
        ],
    )
    assert reponse.status_code == 400

    _passer("adm", "admin")
    agrege = client.get("/admin/etude/ergonomie").json()
    assert agrege["nb_dossiers_mesures"] == 0


def test_les_parts_aberrantes_sont_bornees(client):
    """Un arrondi de navigateur ne doit pas produire une profondeur de 150 %."""
    dossier_id = _ouvrir_un_dossier(client)
    _deposer(
        client,
        dossier_id,
        [
            {
                "zone": ZONE_ANALYSE,
                "profondeur_max": 1.4,
                "part_largeur": -0.2,
                "rang_premiere_visite": 0,
            }
        ],
    )

    _passer("adm", "admin")
    profil = _profil(client.get("/admin/etude/ergonomie").json(), ZONE_ANALYSE)
    assert profil["profondeur_moyenne"] == 1.0
    assert profil["part_largeur_moyenne"] == 0.0
    # Zero n'est pas un rang de visite, c'est une absence de visite.
    assert profil["premiere_visite"]["numerateur"] == 0


def test_un_lot_vide_est_accepte_sans_rien_ecrire(client):
    """Le client envoie a periode fixe ; une periode sans rien a dire n'est pas
    une erreur, et surtout pas de quoi interrompre le praticien."""
    dossier_id = _ouvrir_un_dossier(client)
    reponse = _deposer(client, dossier_id, [])
    assert reponse.status_code == 200
    assert reponse.json()["releves_enregistres"] == 0


def test_on_ne_mesure_pas_l_ecran_d_un_autre_praticien(client):
    dossier_id = _ouvrir_un_dossier(client)
    _passer(AUTRE, "user")
    assert _deposer(
        client, dossier_id, [{"zone": ZONE_ANALYSE, "visible_ms": 1_000}]
    ).status_code == 403


def test_un_praticien_ne_lit_pas_le_profil_d_usage(client):
    """Le profil agrege de tous les confreres ne regarde pas un participant."""
    assert client.get("/admin/etude/ergonomie").status_code == 403


def test_un_dossier_inconnu_sort_en_404(client):
    assert _deposer(
        client, "inexistant", [{"zone": ZONE_ANALYSE, "visible_ms": 1_000}]
    ).status_code == 404


def test_un_dossier_exclu_ne_compte_dans_aucune_mesure(client):
    """Une exclusion qui n'exclut pas donnerait l'illusion d'un corpus propre,
    sur l'ergonomie comme sur les taux de decision."""
    dossier_id = _ouvrir_un_dossier(client)
    _deposer(
        client, dossier_id, [{"zone": ZONE_ANALYSE, "visible_ms": 50_000, "clics": 4}]
    )
    _passer("adm", "admin")
    assert client.get("/admin/etude/ergonomie").json()["nb_dossiers_mesures"] == 1

    client.post(
        f"/admin/etude/dossiers/{dossier_id}/exclusion",
        json={"motif": "Essai de l'administrateur, pas un cas reel"},
    )

    agrege = client.get("/admin/etude/ergonomie").json()
    assert agrege["nb_dossiers_mesures"] == 0
    assert _profil(agrege, ZONE_ANALYSE)["temps_visible_ms_moyen"] is None
