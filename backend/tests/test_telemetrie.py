"""Telemetrie v3 : whitelist (aucun texte libre), agregations exactes, acces admin."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

import main
from auth import get_current_user
from database import get_db_session
from db_models import Base, TelemetrieEvenement, User
from rate_limit import limiter
from telemetrie import agregations
from telemetrie.whitelist import Rejet, valider_evenement

NOW = datetime(2026, 11, 15, 12, 0, tzinfo=timezone.utc)


def _l(user, type_, jours=1, projet=None, **payload):
    return {"user_id": user, "type": type_, "projet_hash": projet, "ts": NOW - timedelta(days=jours, hours=-1), "payload": payload}


# ---------------------------------------------------------------- whitelist
def test_whitelist_accepte_un_evenement_conforme():
    t, p, pid = valider_evenement("projet_genere", {"duree_ms": 8000, "organes": ["sein", "colon_1"], "niveau_service": "N1"}, "proj-1")
    assert t == "projet_genere" and p["organes"] == ["sein", "colon_1"] and pid == "proj-1"


@pytest.mark.parametrize("type_,payload", [
    ("projet_genere", {"dictee": "Madame Dupont, nodule de 12 mm"}),       # cle non whitelistee
    ("projet_genere", {"prelevement": "Mme Dupont"}),                       # chaine libre dans un ident
    ("projet_genere", {"organes": ["Sein gauche"]}),                        # espaces/majuscules
    ("projet_genere", {"niveau_service": "tres_bien"}),                     # hors enum
    ("projet_genere", {"duree_ms": "1200"}),                                # chaine au lieu d'un nombre
    ("projet_genere", {"duree_ms": True}),                                  # booleen n'est pas un nombre
    ("projet_genere", {"duree_ms": 10**9}),                                 # hors bornes
    ("projet_genere", {"duree_ms": float("nan")}),
    ("feedback", {"sens": "negatif", "motifs": ["il a invente une taille"]}),
    ("feedback", {"sens": "negatif", "motifs": ["dupont"]}),                # ident valide mais motif inconnu
    ("export", {"sans_retouche": "oui"}),
    ("erreur", {"code": "reseau", "etape": "x" * 80}),
    ("type_inconnu", {}),
    ("trou_comble", {"champ_id": "taille_tumorale", "valeur": "12"}),       # une valeur de champ = donnee medicale
])
def test_whitelist_rejette_le_texte_libre(type_, payload):
    with pytest.raises(Rejet):
        valider_evenement(type_, payload)


def test_whitelist_rejette_un_projet_id_libre():
    with pytest.raises(Rejet):
        valider_evenement("export", {}, "Dupont Marie 1950")


# ---------------------------------------------------------------- agregations exactes
def jeu():
    L = []
    for i in range(10):
        L.append(_l("u1" if i < 6 else "u2", "projet_genere", jours=i % 3 + 1, projet=f"p{i}", duree_ms=1000 * (i + 1),
                    organes=["sein"] if i < 7 else ["colon"], niveau_service="N0" if i < 8 else "N2"))
    for i in range(4):
        L.append(_l("u1", "export", jours=1, projet=f"p{i}", duree_depuis_generation_ms=10000 * (i + 1), sans_retouche=i < 3))
    for _ in range(5):
        L.append(_l("u1", "element_edite", element_type="phrase", statut="reformule", niveau="basse"))
    L += [_l("u1", "element_edite", element_type="trou", statut="a_completer", niveau="moyenne")] * 5
    L += [_l("u1", "trou_ignore", champ_id="grade")] * 7 + [_l("u1", "trou_comble", champ_id="grade")] * 3
    L += [_l("u2", "alerte_ignoree", alerte_type="unite")] * 2 + [_l("u2", "alerte_resolue", alerte_type="unite")] * 3
    L += [_l("u2", "correction_acceptee")] * 3 + [_l("u2", "correction_rejetee")] * 2
    L += [_l("u2", "feedback", sens="negatif", motifs=["omission"])] * 3 + [_l("u2", "feedback", sens="positif")] * 2
    L += [_l("u2", "erreur", code="stt")]
    return L


def test_agregations_exactes():
    s = agregations.synthese(jeu(), 7, NOW, {"u1": "a@x.fr"})
    k = s["kpi"]
    assert k["projets_generes"] == 10 and k["utilisateurs_actifs"] == 2
    assert k["temps_median_generation_ms"] == 5500.0
    assert k["temps_median_export_ms"] == 25000.0
    assert k["taux_exports_sans_retouche"] == 0.75
    assert k["retouches_moyennes_par_projet"] == 1.0
    assert {x["valeur"]: x["retouches"] for x in s["retouches"]["par_type_element"]} == {"phrase": 5, "trou": 5}
    assert s["trous"] == [{"champ_id": "grade", "combles": 3, "ignores": 7, "taux_ignore": 0.7}]
    assert s["alertes"][0] == {"alerte_type": "unite", "resolues": 3, "ignorees": 2, "taux_ignore": 0.4}
    assert s["corrections"] == {"acceptees": 3, "rejetees": 2, "precision": 0.6}
    assert s["feedback"]["positif"] == 2 and s["feedback"]["motifs"] == [{"motif": "omission", "n": 3}]
    assert s["organes"][0] == {"organe": "sein", "n": 7}
    assert {x["niveau"]: x["projets"] for x in s["service"]["niveaux"]}["N2"] == 2
    assert len(s["series"]) == 7 and sum(x["projets"] for x in s["series"]) == 10
    assert s["top_utilisateurs"][0]["compte"] == "a@x.fr" and s["kpi"]["mau"] == 2


def test_recommandations_calculees():
    ids = {r["id"] for r in agregations.recommandations(agregations.synthese(jeu(), 7, NOW))}
    assert {"champ_ignore_grade", "alerte_ignoree_unite", "correcteur_precision", "feedback_negatif"} <= ids


def test_pas_de_recommandation_sur_trop_peu_de_donnees():
    s = agregations.synthese([_l("u", "trou_ignore", champ_id="grade")] * 3, 7, NOW)
    assert agregations.recommandations(s) == []


def test_variation_vs_periode_precedente():
    L = [_l("u", "projet_genere", jours=2)] * 3 + [_l("u", "projet_genere", jours=10)] * 2
    assert agregations.synthese(L, 7, NOW)["kpi"]["variation"]["projets_generes"] == 0.5


# ---------------------------------------------------------------- API
def _user(i, role):
    u = User(); u.id = i; u.email = f"{i}@marc.test"; u.name = i; u.role = role
    return u


@pytest.fixture
def client(tmp_path):
    moteur = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 't.db'}", poolclass=NullPool)
    fab = async_sessionmaker(moteur, expire_on_commit=False)

    async def _base():
        async with fab() as s:
            yield s

    async def _init():
        async with moteur.begin() as c:
            await c.run_sync(Base.metadata.create_all)
        async with fab() as s:
            s.add(User(id="prat", email="prat@marc.test", password_hash="x", name="P", role="user"))
            await s.commit()

    async def _lire():
        async with fab() as s:
            return (await s.execute(select(TelemetrieEvenement))).scalars().all()

    app = main.app
    app.dependency_overrides[get_db_session] = _base
    app.dependency_overrides[get_current_user] = lambda: _user("prat", "user")
    limiter.reset()
    with TestClient(app) as c:
        c.portal.call(_init)
        c.lire = lambda: c.portal.call(_lire)
        yield c
        app.dependency_overrides.clear()
        c.portal.call(moteur.dispose)
    limiter.reset()


def test_post_lot_filtre_et_ne_stocke_que_le_conforme(client):
    r = client.post("/v3/telemetrie/evenements", json={"evenements": [
        {"type": "projet_genere", "payload": {"duree_ms": 5000, "organes": ["sein"]}, "projet_id": "abc-123"},
        {"type": "projet_genere", "payload": {"dictee": "Mme Martin"}},
        {"type": "trou_ignore", "payload": {"champ_id": "grade"}},
    ]})
    assert r.status_code == 200 and r.json() == {"acceptes": 2, "rejetes": 1}
    lignes = client.lire()
    assert len(lignes) == 2
    assert "abc-123" not in str([l.projet_hash for l in lignes]) and lignes[0].projet_hash
    assert "Martin" not in str([l.payload for l in lignes])


def test_post_exige_l_authentification(client):
    main.app.dependency_overrides.pop(get_current_user)
    assert client.post("/v3/telemetrie/evenements", json={"evenements": []}).status_code == 401


def test_post_lot_trop_gros_refuse(client):
    ev = {"type": "export", "payload": {}}
    assert client.post("/v3/telemetrie/evenements", json={"evenements": [ev] * 51}).status_code == 422


def test_rate_limit(client):
    codes = [client.post("/v3/telemetrie/evenements", json={"evenements": []}).status_code for _ in range(62)]
    assert codes[0] == 200 and codes[-1] == 429


def test_admin_uniquement(client):
    for u in ("synthese?periode=7j", "recommandations"):
        assert client.get(f"/v3/admin/telemetrie/{u}").status_code == 403
    main.app.dependency_overrides[get_current_user] = lambda: _user("adm", "admin")
    r = client.get("/v3/admin/telemetrie/synthese?periode=30j")
    assert r.status_code == 200 and r.json()["periode_jours"] == 30
    assert client.get("/v3/admin/telemetrie/synthese?periode=1j").status_code == 422
    assert client.get("/v3/admin/telemetrie/recommandations").json()["recommandations"] == []


def test_de_bout_en_bout_api(client):
    client.post("/v3/telemetrie/evenements", json={"evenements": [
        {"type": "projet_genere", "payload": {"duree_ms": 4000}, "projet_id": "p1"},
        {"type": "export", "payload": {"sans_retouche": True, "duree_depuis_generation_ms": 9000}, "projet_id": "p1"},
    ]})
    main.app.dependency_overrides[get_current_user] = lambda: _user("adm", "admin")
    k = client.get("/v3/admin/telemetrie/synthese?periode=7j").json()["kpi"]
    assert k["projets_generes"] == 1 and k["taux_exports_sans_retouche"] == 1.0
    assert client.get("/v3/admin/telemetrie/synthese").json()["top_utilisateurs"][0]["compte"] == "prat@marc.test"
