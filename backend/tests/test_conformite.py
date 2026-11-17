"""Conformite ISO 15189:2022 : chaine d'audit inviolable, validation, aucune donnee textuelle, controle d'acces."""
from __future__ import annotations

import hashlib

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

import main
from auth import get_current_user
from conformite import chaine, tracabilite
from conformite.metadonnees import MetadonneeInvalide, valider_payload
from database import get_db_session
from db_models import (Base, ConformiteAudit, ConformiteHabilitation, ConformiteKbVersion,
                       ConformiteNonConformite, ConformiteValidation, User)
from projet.orchestrateur import projet_de_secours
from rate_limit import limiter

H = lambda s: hashlib.sha256(s.encode()).hexdigest()  # noqa: E731
DICTEE_SENTINELLE = "Madame Dupont nodule du sein de 12 mm adenocarcinome"


def _user(i, role):
    u = User(id=i, email=f"{i}@marc.test", password_hash="x", name=i, role=role)
    u.is_active = True
    return u


@pytest.fixture
def client(tmp_path):
    moteur = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'c.db'}", poolclass=NullPool)
    fab = async_sessionmaker(moteur, expire_on_commit=False)

    async def _base():
        async with fab() as s:
            yield s

    async def _init():
        async with moteur.begin() as c:
            await c.run_sync(Base.metadata.create_all)
        async with fab() as s:
            for i, r in (("prat", "user"), ("adm", "admin"), ("val", "user")):
                s.add(User(id=i, email=f"{i}@marc.test", password_hash="x", name=i, role=r))
            await s.commit()

    async def _sql(f):
        async with fab() as s:
            return await f(s)

    app = main.app
    app.dependency_overrides[get_db_session] = _base
    qui = {"u": "val"}
    app.dependency_overrides[get_current_user] = lambda: _user(qui["u"], "admin" if qui["u"] == "adm" else "user")
    limiter.reset()
    with TestClient(app) as c:
        c.portal.call(_init)
        c.sql = lambda f: c.portal.call(_sql, f)
        c.en_tant_que = lambda u: qui.update(u=u)
        yield c
        app.dependency_overrides.clear()
        c.portal.call(moteur.dispose)
    limiter.reset()
    tracabilite.definir_kb_en_service(None)


def brut(sql):
    async def f(s):
        await s.execute(text(sql))
        await s.commit()
    return f


def habiliter(c, uid="val"):
    c.en_tant_que("adm")
    assert c.put(f"/v3/conformite/habilitations/{uid}", json={"habilite": True}).status_code == 200
    c.en_tant_que(uid)


def corps(emp="a", bloq=0, trous=0, **kw):
    return {"projet_id": "proj-1", "empreinte_sha256": H(emp), "nb_alertes_bloquantes_ouvertes": bloq,
            "nb_trous_ouverts": trous, "versions": {"pipeline": "3.0.0+abc1234", "kb": "3.0.0", "modeles": {"redacteur": "mistral-large-2512"}}, **kw}


# ------------------------------------------------------------------ tracabilite
def test_bloc_tracabilite_du_projet():
    p = projet_de_secours(DICTEE_SENTINELLE, "test")
    t = p.tracabilite
    assert t and t.id == p.id and t.statut == "brouillon"
    assert t.empreinte_dictee_corrigee_sha256 == H(DICTEE_SENTINELLE)
    assert t.version_pipeline.startswith("3.0.0") and t.horodatage_utc.endswith("Z")
    assert t.kb_version and len(t.kb_empreinte_sha256) == 64
    assert DICTEE_SENTINELLE not in t.model_dump_json()


# ------------------------------------------------------------------ chaine d'audit
def test_chaine_intacte_puis_alteration_detectee(client):
    habiliter(client)
    assert client.post("/v3/conformite/validations", json=corps("v1")).status_code == 201
    assert client.post("/v3/conformite/validations", json=corps("v2")).status_code == 201
    client.en_tant_que("adm")
    v = client.get("/v3/conformite/audit/verification").json()
    assert v["ok"] and v["nb_entrees"] >= 3
    # alteration directe en base (hors ORM) d'une entree du milieu
    client.sql(brut("UPDATE conformite_audit SET acteur_id='intrus' WHERE seq=2"))
    v = client.get("/v3/conformite/audit/verification").json()
    assert not v["ok"] and v["rupture_seq"] == 2 and "altéré" in v["motif"]


def test_suppression_d_une_entree_detectee(client):
    habiliter(client)
    client.post("/v3/conformite/validations", json=corps("v1"))
    client.en_tant_que("adm")
    client.sql(brut("DELETE FROM conformite_audit WHERE seq=1"))
    assert not client.get("/v3/conformite/audit/verification").json()["ok"]


def test_orm_refuse_la_modification_du_journal(client):
    habiliter(client)

    async def f(s):
        e = (await s.execute(select(ConformiteAudit))).scalars().first()
        e.type = "validation"
        await s.commit()
    with pytest.raises(RuntimeError):
        client.sql(f)


def test_export_csv_et_lecture(client):
    habiliter(client)
    client.en_tant_que("adm")
    r = client.get("/v3/conformite/audit/export.csv")
    assert r.status_code == 200 and r.text.startswith("seq;ts;type") and "habilitation" in r.text
    assert client.get("/v3/conformite/audit").json()["total"] >= 1


# ------------------------------------------------------------------ validation
def test_refus_sans_habilitation(client):
    client.en_tant_que("prat")
    assert client.post("/v3/conformite/validations", json=corps()).status_code == 403


def test_refus_avec_blocages_puis_derogation(client):
    habiliter(client)
    r = client.post("/v3/conformite/validations", json=corps(bloq=1))
    assert r.status_code == 409 and r.json()["detail"]["blocages"]["alertes_bloquantes"] == 1
    assert client.post("/v3/conformite/validations", json=corps(trous=2)).status_code == 409
    assert client.post("/v3/conformite/validations", json=corps(trous=2, derogation="texte libre")).status_code == 422
    r = client.post("/v3/conformite/validations", json=corps(trous=2, derogation="information_indisponible_au_dossier"))
    assert r.status_code == 201 and r.json()["derogation"] == "information_indisponible_au_dossier"
    client.en_tant_que("adm")
    types = [e["type"] for e in client.get("/v3/conformite/audit").json()["entrees"]]
    assert "validation" in types and "derogation" in types


def test_revision_liee_a_la_validation_precedente(client):
    habiliter(client)
    a = client.post("/v3/conformite/validations", json=corps("v1")).json()
    assert a["revision"] == 1 and a["precedente_id"] is None
    assert client.post("/v3/conformite/validations", json=corps("v1")).status_code == 409  # meme texte
    b = client.post("/v3/conformite/validations", json=corps("v2")).json()
    assert b["revision"] == 2 and b["precedente_id"] == a["id"]
    assert [v["revision"] for v in client.get("/v3/conformite/validations/proj-1").json()["validations"]] == [1, 2]
    client.en_tant_que("adm")
    assert "revision" in [e["type"] for e in client.get("/v3/conformite/audit").json()["entrees"]]


def test_empreinte_invalide_refusee(client):
    habiliter(client)
    assert client.post("/v3/conformite/validations", json={**corps(), "empreinte_sha256": "pas-un-hash"}).status_code == 422


def test_generation_idempotente(client):
    b = {"projet_id": "proj-9", "versions": {"pipeline": "3.0.0", "kb": "3.0.0"}, "empreinte_dictee_corrigee_sha256": H("x"), "niveau_service": "N1"}
    assert client.post("/v3/conformite/generations", json=b).json()["enregistre"] is True
    assert client.post("/v3/conformite/generations", json=b).json()["enregistre"] is False


# ------------------------------------------------------------------ registre kb
def test_registre_kb_cycle_de_vie(client):
    client.en_tant_que("adm")
    k = client.post("/v3/conformite/kb/versions/enregistrer").json()
    v = k["version"]
    assert k["statut"] == "brouillon" and len(k["empreinte_sha256"]) == 64
    assert client.post(f"/v3/conformite/kb/versions/{v}/mettre-en-service").status_code == 409  # pas approuvee
    assert client.post(f"/v3/conformite/kb/versions/{v}/approuver").json()["statut"] == "approuvee"
    assert client.post(f"/v3/conformite/kb/versions/{v}/mettre-en-service").json()["statut"] == "en_service"
    assert client.get("/v3/conformite/kb/en-service").json()["version"] == v
    assert tracabilite.construire(projet_id="x", dictee_corrigee="y", niveau_service="N0", modeles={}).kb_statut == "en_service"
    assert client.post(f"/v3/conformite/kb/versions/{v}/retirer").json()["statut"] == "retiree"
    assert client.get("/v3/conformite/kb/en-service").json()["version"] is None


# ------------------------------------------------------------------ non-conformites
def test_non_conformite_enum_et_liste_admin(client):
    ok = {"categorie": "fabrication", "gravite": "critique", "etape": "redacteur", "projet_id": "proj-1", "organe": "sein"}
    assert client.post("/v3/conformite/non-conformites", json=ok).status_code == 201
    assert client.post("/v3/conformite/non-conformites", json={**ok, "categorie": "il a invente une taille"}).status_code == 422
    assert client.post("/v3/conformite/non-conformites", json={**ok, "organe": "Sein gauche de Mme Dupont"}).status_code == 422
    assert client.get("/v3/conformite/non-conformites").status_code == 403
    client.en_tant_que("adm")
    r = client.get("/v3/conformite/non-conformites").json()
    assert r["total"] == 1 and r["par_categorie"] == {"fabrication": 1}
    nc = r["non_conformites"][0]["id"]
    assert client.patch(f"/v3/conformite/non-conformites/{nc}", json={"statut": "cloturee"}).json()["statut"] == "cloturee"


# ------------------------------------------------------------------ aucune donnee textuelle
def test_aucune_donnee_textuelle_dans_les_tables(client):
    habiliter(client)
    client.post("/v3/conformite/generations", json={"projet_id": "proj-1", "empreinte_dictee_corrigee_sha256": H(DICTEE_SENTINELLE)})
    client.post("/v3/conformite/validations", json=corps(DICTEE_SENTINELLE))
    client.post("/v3/conformite/non-conformites", json={"categorie": "autre", "gravite": "mineure", "projet_id": "proj-1"})
    # tentatives d'injection de texte : toutes refusees
    for bad in ({"projet_id": DICTEE_SENTINELLE}, {"versions": {"kb": DICTEE_SENTINELLE}}):
        assert client.post("/v3/conformite/validations", json={**corps("z"), **bad}).status_code == 422
    client.en_tant_que("adm")
    client.post("/v3/conformite/kb/versions/enregistrer")

    async def dump(s):
        out = []
        for m in (ConformiteAudit, ConformiteHabilitation, ConformiteValidation, ConformiteKbVersion, ConformiteNonConformite):
            for row in (await s.execute(select(m))).scalars():
                out.append(str({c.name: getattr(row, c.name) for c in m.__table__.columns}))
        return "\n".join(out)
    contenu = client.sql(dump)
    assert contenu
    for mot in ("Dupont", "nodule", "adenocarcinome", "12 mm"):
        assert mot not in contenu
    assert "proj-1" not in contenu  # l'id de projet n'est stocke que sous forme de hash sale


def test_garde_fou_metadonnees():
    assert valider_payload({"a_b": 1, "ok": True, "v": "3.0.0+abc", "l": ["x", "y"]})
    for bad in ({"t": "du texte libre"}, {"t": "é"}, {"T": "x"}, {"t": {"u": "a b"}}, {"t": 1.5}):
        with pytest.raises(MetadonneeInvalide):
            valider_payload(bad)


# ------------------------------------------------------------------ controle d'acces
@pytest.mark.parametrize("methode,url", [
    ("get", "/v3/conformite/audit"), ("get", "/v3/conformite/audit/verification"), ("get", "/v3/conformite/audit/export.csv"),
    ("get", "/v3/conformite/kb/versions"), ("post", "/v3/conformite/kb/versions/enregistrer"),
    ("post", "/v3/conformite/kb/versions/3.0.0/approuver"), ("post", "/v3/conformite/kb/versions/3.0.0/mettre-en-service"),
    ("get", "/v3/conformite/habilitations"), ("put", "/v3/conformite/habilitations/val"), ("get", "/v3/conformite/non-conformites"),
])
def test_routes_admin_refusees_aux_non_admin(client, methode, url):
    client.en_tant_que("prat")
    r = getattr(client, methode)(url, **({"json": {"habilite": True}} if methode == "put" else {}))
    assert r.status_code == 403


def test_authentification_requise(client):
    main.app.dependency_overrides.pop(get_current_user)
    for u in ("/v3/conformite/moi", "/v3/conformite/kb/en-service"):
        assert client.get(u).status_code == 401
    assert client.post("/v3/conformite/validations", json=corps()).status_code == 401


def test_habilitation_changement_journalise_et_revocable(client):
    habiliter(client)
    client.en_tant_que("adm")
    client.put("/v3/conformite/habilitations/val", json={"habilite": False})
    client.en_tant_que("val")
    assert client.get("/v3/conformite/moi").json()["habilite"] is False
    assert client.post("/v3/conformite/validations", json=corps()).status_code == 403
    client.en_tant_que("adm")
    assert [e["type"] for e in client.get("/v3/conformite/audit").json()["entrees"]].count("habilitation") == 2
