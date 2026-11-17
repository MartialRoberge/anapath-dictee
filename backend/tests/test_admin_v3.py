"""Admin v3 unifie : signalements (dedoublonnage, donnees patient, recopie), routes /v3/admin, avis anciens, sante."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

import main
from admin_v3 import retours
from admin_v3.signalements import detecter_donnee_patient, quasi_identiques, recopier_non_conformites
from auth import get_current_user
from conformite import chaine, tracabilite
from database import get_db_session
from db_models import (Base, ConformiteAudit, ConformiteHabilitation, ConformiteNonConformite, Report, Signalement,
                       TelemetrieEvenement, User)
from etude.models import EtudeDossier, EtudeReponseQuestionnaire, EtudeSession
from rate_limit import limiter

SENTINELLE = "Madame Dupont adenocarcinome du sein 12 mm"
MAINTENANT = datetime.now(timezone.utc)


def _user(i, role):
    u = User(id=i, email=f"{i}@marc.test", password_hash="x", name=i, role=role)
    u.is_active = True
    return u


@pytest.fixture
def client(tmp_path):
    moteur = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'a.db'}", poolclass=NullPool)
    fab = async_sessionmaker(moteur, expire_on_commit=False)

    async def _base():
        async with fab() as s:
            yield s

    async def _init():
        async with moteur.begin() as c:
            await c.run_sync(Base.metadata.create_all)
        async with fab() as s:
            for i, r in (("prat", "user"), ("adm", "admin"), ("autre", "user")):
                s.add(User(id=i, email=f"{i}@marc.test", password_hash="x", name=f"Nom {i}", role=r))
            await s.commit()

    async def _sql(f):
        async with fab() as s:
            return await f(s)

    app = main.app
    app.dependency_overrides[get_db_session] = _base
    qui = {"u": "prat"}
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


def ajouter(c, *objets):
    async def f(s):
        s.add_all(objets)
        await s.commit()
    c.sql(f)


def signaler(c, message="Le bouton Exporter ne répond plus", categorie="dysfonctionnement", **extra):
    return c.post("/v3/signalements", json={"categorie": categorie, "message": message, **extra})


# --------------------------------------------------------------------------- donnees patient
@pytest.mark.parametrize("texte", [
    "Mme Dupont a été mal codée",
    "le patient est né le 12 mars",
    "date de naissance incorrecte",
    "née en 1964",
    "NIR 2 64 03 75 116 058 44 affiché",
    "1 85 05 78 006 084 36",
    "appelez-moi au 06 12 34 56 78",
    "contact jean.dupont@hopital.fr",
    "dossier du 12/03/1964 faux",
    "examen du 2024-03-12",
    "prélevé le 3 mars 2024",
    "Patient : Martin",
    "Monsieur Durand",
])
def test_detecte_donnees_patient(texte):
    assert detecter_donnee_patient(texte) is not None


@pytest.mark.parametrize("texte", [
    "Le bouton Exporter ne répond plus",
    "La taille 12 mm est mal reportée dans la conclusion",
    "Le code ADICAP proposé est faux pour le côlon",
    "Il manque une option dans le menu 2",
    "Trop lent : 20 secondes pour générer",
])
def test_messages_ordinaires_acceptes(texte):
    assert detecter_donnee_patient(texte) is None


def test_refus_donnee_patient_message_clair(client):
    r = signaler(client, "Mme Dupont née le 12/03/1964 est mal reportée")
    assert r.status_code == 422
    assert "protéger les patients" in r.json()["detail"]
    assert client.sql(lambda s: _compter(s)) == 0


async def _compter(s):
    return len((await s.execute(select(Signalement))).scalars().all())


def test_message_vide_ou_trop_long(client):
    assert signaler(client, "   ").status_code == 422
    r = signaler(client, "a" * 1001)
    assert r.status_code == 422 and "1000" in r.json()["detail"]
    assert signaler(client, "a" * 1000).status_code == 200


def test_categorie_inconnue(client):
    assert signaler(client, categorie="autre").status_code == 422


def test_signaler_exige_connexion_et_champs_techniques(client):
    assert signaler(client, ecran="Éditeur !").status_code == 422
    assert signaler(client, projet_id="a b").status_code == 422
    r = signaler(client, projet_id="proj_1", ecran="editeur", version_app="3.0.0")
    assert r.status_code == 200
    ligne = client.sql(lambda s: _premiere(s))
    assert ligne.projet_hash and "proj_1" not in ligne.projet_hash
    assert (ligne.ecran, ligne.version_app, ligne.statut, ligne.user_id) == ("editeur", "3.0.0", "ouvert", "prat")


async def _premiere(s):
    return (await s.execute(select(Signalement))).scalars().first()


# --------------------------------------------------------------------------- dedoublonnage
def test_dedoublonnage_renvoie_l_existant(client):
    a = signaler(client, projet_id="p1").json()
    assert a["doublon_de"] is None
    b = signaler(client, "Le bouton Exporter ne répond plus !", projet_id="p1").json()
    assert b == {"id": a["id"], "doublon_de": a["id"]}
    assert client.sql(_compter) == 1


def test_pas_de_doublon_si_autre_categorie_projet_utilisateur_ou_message(client):
    a = signaler(client, projet_id="p1").json()["id"]
    assert signaler(client, categorie="amelioration", projet_id="p1").json()["doublon_de"] is None
    assert signaler(client, projet_id="p2").json()["doublon_de"] is None
    assert signaler(client).json()["doublon_de"] is None  # sans projet
    assert signaler(client, "Le code ADICAP proposé est faux", projet_id="p1").json()["doublon_de"] is None
    client.en_tant_que("autre")
    assert signaler(client, projet_id="p1").json()["doublon_de"] is None
    assert a


def test_plus_de_dix_minutes_ce_n_est_plus_un_doublon(client):
    a = signaler(client).json()["id"]

    async def vieillir(s):
        ligne = await s.get(Signalement, a)
        ligne.cree_le = datetime.now(timezone.utc) - timedelta(minutes=11)
        await s.commit()
    client.sql(vieillir)
    assert signaler(client).json()["doublon_de"] is None
    assert client.sql(_compter) == 2


def test_quasi_identiques():
    assert quasi_identiques("Le bouton Exporter ne répond plus", "le bouton exporter ne repond plus.")
    assert not quasi_identiques("Le bouton Exporter ne répond plus", "Le code ADICAP est faux")


# --------------------------------------------------------------------------- non-conformites : recopie + compatibilite
def _nc(i, statut="ouverte", ts="2026-03-01T10:00:00.000000Z", cat="faux_positif"):
    return ConformiteNonConformite(id=i, ts=ts, user_id="prat", projet_hash="abcd", categorie=cat, gravite="majeure",
                                   etape="verificateur", organe="sein", statut=statut, kb_version="1.2", version_pipeline="3.0.0")


def _recopier(c):
    async def f(s):
        n = await s.run_sync(lambda sync: recopier_non_conformites(sync.connection()))
        await s.commit()
        return n
    return c.sql(f)


def test_recopie_idempotente(client):
    ajouter(client, _nc("nc-1"), _nc("nc-2", "en_analyse"), _nc("nc-3", "cloturee"))
    assert _recopier(client) == 3
    assert _recopier(client) == 0
    lignes = {s.id: s for s in client.sql(_toutes)}
    assert {k: v.statut for k, v in lignes.items()} == {"nc-1": "ouvert", "nc-2": "en_cours", "nc-3": "traite"}
    assert all(s.categorie == "non_conformite" and s.categorie_iso == "faux_positif" and s.origine_nc_id == s.id for s in lignes.values())
    assert lignes["nc-1"].gravite == "majeure" and lignes["nc-1"].cree_le.year == 2026
    # la table ancienne est intacte
    assert len(client.sql(_anciennes)) == 3
    # une NC ajoutee ensuite est recopiee seule
    ajouter(client, _nc("nc-4"))
    assert _recopier(client) == 1
    assert len(client.sql(_toutes)) == 4


async def _toutes(s):
    return list((await s.execute(select(Signalement))).scalars())


async def _anciennes(s):
    return list((await s.execute(select(ConformiteNonConformite))).scalars())


def test_routes_conformite_lisent_et_ecrivent_signalements(client):
    ajouter(client, _nc("vieille"))
    _recopier(client)
    r = client.post("/v3/conformite/non-conformites", json={"projet_id": "p1", "categorie": "code_errone", "gravite": "critique", "etape": "codeur"})
    assert r.status_code == 201 and r.json()["statut"] == "ouverte"
    nouvelle = r.json()["id"]
    # ecrit dans signalements, plus dans l'ancienne table
    assert any(s.id == nouvelle and s.categorie == "non_conformite" for s in client.sql(_toutes))
    assert [n.id for n in client.sql(_anciennes)] == ["vieille"]
    # doublon (meme categorie/gravite/projet) < 10 min : meme id, une seule ligne
    assert client.post("/v3/conformite/non-conformites", json={"projet_id": "p1", "categorie": "code_errone", "gravite": "critique"}).json()["id"] == nouvelle
    client.en_tant_que("adm")
    lst = client.get("/v3/conformite/non-conformites").json()
    assert lst["total"] == 2 and lst["par_categorie"] == {"faux_positif": 1, "code_errone": 1}
    nc = next(n for n in lst["non_conformites"] if n["id"] == nouvelle)
    assert set(nc) == {"id", "ts", "user_id", "projet_hash", "categorie", "gravite", "etape", "organe", "statut", "kb_version", "version_pipeline"}
    assert nc["categorie"] == "code_errone" and nc["gravite"] == "critique" and nc["ts"].endswith("Z")
    assert client.get("/v3/conformite/non-conformites?statut=en_analyse").json()["total"] == 0
    p = client.patch(f"/v3/conformite/non-conformites/{nouvelle}", json={"statut": "en_analyse"})
    assert p.status_code == 200 and p.json()["statut"] == "en_analyse"
    assert client.get("/v3/conformite/non-conformites?statut=en_analyse").json()["total"] == 1
    assert client.sql(lambda s: _get(s, nouvelle)).statut == "en_cours"
    # un signalement libre n'est pas une non-conformite ISO a patcher par cette route
    sid = signaler(client, categorie="amelioration").json()["id"]
    assert client.patch(f"/v3/conformite/non-conformites/{sid}", json={"statut": "cloturee"}).status_code == 404


async def _get(s, i):
    return await s.get(Signalement, i)


# --------------------------------------------------------------------------- droits : 403 pour un non-admin
@pytest.mark.parametrize("methode,url,corps", [
    ("get", "/v3/admin/vue-ensemble", None),
    ("get", "/v3/admin/retours", None),
    ("patch", "/v3/admin/signalements/x", {"statut": "traite"}),
    ("get", "/v3/admin/utilisateurs", None),
    ("get", "/v3/admin/etude", None),
    ("get", "/v3/admin/sante", None),
])
def test_routes_admin_refusees_aux_non_admins(client, methode, url, corps):
    r = getattr(client, methode)(url, **({"json": corps} if corps else {}))
    assert r.status_code == 403


def test_admin_non_authentifie_refuse():
    main.app.dependency_overrides.clear()
    with TestClient(main.app) as c:
        assert c.get("/v3/admin/vue-ensemble").status_code in (401, 503)
        assert c.post("/v3/signalements", json={"categorie": "amelioration", "message": "x"}).status_code in (401, 503)


# --------------------------------------------------------------------------- jeu de donnees ancien
def _semer_ancien(c):
    maintenant = datetime.now(timezone.utc)
    avis = json.dumps({"feedback": {"rating": 2, "comment": "La mise en forme est lente", "timestamp": (maintenant - timedelta(hours=3)).isoformat()},
                       "corrections": [{"before": SENTINELLE, "after": SENTINELLE + " corrigé", "timestamp": "x"}]})
    ajouter(
        c,
        Report(id="r1", user_id="prat", raw_transcription=SENTINELLE, structured_report=SENTINELLE, organe_detecte="sein",
               completeness_warnings=avis, created_at=maintenant - timedelta(days=1)),
        Report(id="r2", user_id="prat", raw_transcription=SENTINELLE, structured_report=SENTINELLE,
               completeness_warnings=json.dumps({"feedback": {"rating": 5, "comment": ""}}), created_at=maintenant - timedelta(days=2)),
        Report(id="r3", user_id="autre", raw_transcription=SENTINELLE, structured_report=SENTINELLE,
               completeness_warnings="pas du json {feedback", created_at=maintenant - timedelta(days=40)),
        Report(id="r4", user_id="fantome", raw_transcription=SENTINELLE, structured_report=SENTINELLE, created_at=maintenant),
        EtudeSession(id="s1", praticien_id="prat", debut=maintenant - timedelta(days=1)),
        EtudeDossier(id="d1", session_id="s1", commentaire_validation="Les menus sont clairs", cree_a=maintenant - timedelta(days=1)),
        EtudeDossier(id="d2", session_id="s1", commentaire_validation="essai à ignorer", exclu=True, cree_a=maintenant),
        EtudeReponseQuestionnaire(id="q1", praticien_id="prat", dossier_id=None, questionnaire="fin_etude", item="intention_04",
                                  valeur="Le temps de chargement"),
        EtudeReponseQuestionnaire(id="q2", praticien_id="prat", dossier_id="d1", questionnaire="par_cas", item="par_cas_01b",
                                  valeur=SENTINELLE),  # item libre exclu : peut citer la dictee
        EtudeReponseQuestionnaire(id="q3", praticien_id="prat", dossier_id="d1", questionnaire="par_cas", item="par_cas_07", valeur="Bien"),
        TelemetrieEvenement(id="t1", user_id="adm", type="projet_genere", payload={"duree_ms": 4000}, ts=maintenant - timedelta(hours=2)),
        TelemetrieEvenement(id="t2", user_id="adm", type="projet_genere", payload={"duree_ms": 6000}, ts=maintenant - timedelta(hours=1)),
        TelemetrieEvenement(id="t3", user_id="adm", type="element_edite", payload={}, ts=maintenant - timedelta(hours=1)),
        TelemetrieEvenement(id="t4", user_id="prat", type="feedback", payload={"sens": "negatif", "motifs": ["omission"]}, ts=maintenant - timedelta(minutes=5)),
        TelemetrieEvenement(id="t5", user_id="autre", type="feedback", payload={"sens": "positif"}, ts=maintenant - timedelta(minutes=9)),
    )


def test_vue_ensemble(client):
    _semer_ancien(client)
    client.en_tant_que("prat")
    signaler(client)
    client.en_tant_que("adm")
    j = client.get("/v3/admin/vue-ensemble?periode=7j").json()
    assert set(j) == {"periode", "kpi", "serie", "origines"} and j["periode"] == "7j"
    assert set(j["kpi"]) == {"utilisateurs_actifs", "utilisateurs_total", "projets_v3", "comptes_rendus_anciens", "dossiers_etude",
                             "notes_utile", "notes_a_ameliorer", "signalements_ouverts", "duree_mediane_generation_ms",
                             "modifications_moyennes_par_projet"}
    k = j["kpi"]
    assert (k["projets_v3"], k["comptes_rendus_anciens"], k["dossiers_etude"]) == (2, 3, 2)  # r1, r2, r4 ; d1, d2
    assert (k["notes_utile"], k["notes_a_ameliorer"], k["signalements_ouverts"]) == (1, 1, 1)
    assert k["duree_mediane_generation_ms"] == 5000.0 and k["modifications_moyennes_par_projet"] == 0.5
    assert k["utilisateurs_total"] == 3 and k["utilisateurs_actifs"] == 4  # adm, prat, autre, fantome
    assert j["origines"] == {"v3": True, "ancienne_version": True, "etude": True}
    assert len(j["serie"]) == 7 and set(j["serie"][0]) == {"jour", "projets_v3", "comptes_rendus_anciens", "utilisateurs_actifs"}
    assert sum(x["comptes_rendus_anciens"] for x in j["serie"]) == 3 and sum(x["projets_v3"] for x in j["serie"]) == 2
    assert j["serie"][-1]["jour"] == datetime.now(timezone.utc).date().isoformat()
    tout = client.get("/v3/admin/vue-ensemble?periode=tout").json()
    assert tout["kpi"]["comptes_rendus_anciens"] == 4 and len(tout["serie"]) >= 41
    assert client.get("/v3/admin/vue-ensemble?periode=1an").status_code == 422
    assert client.get("/v3/admin/vue-ensemble").json()["periode"] == "30j"


def test_vue_ensemble_base_vide(client):
    client.en_tant_que("adm")
    j = client.get("/v3/admin/vue-ensemble?periode=tout").json()
    assert j["origines"] == {"v3": False, "ancienne_version": False, "etude": False}
    assert j["kpi"]["duree_mediane_generation_ms"] is None and j["kpi"]["modifications_moyennes_par_projet"] is None
    assert len(j["serie"]) == 1


def test_retours_flux_unifie_sans_fuite_medicale(client):
    _semer_ancien(client)
    client.en_tant_que("prat")
    sid = signaler(client).json()["id"]
    client.en_tant_que("adm")
    r = client.get("/v3/admin/retours")
    assert SENTINELLE not in r.text and "Dupont" not in r.text and "corrigé" not in r.text
    j = r.json()
    assert j["page"] == 1 and j["total"] == len(j["items"]) == 8
    assert {i["id"] for i in j["items"]} == {f"signalement:{sid}", "note:t4", "note:t5", "avis:r1", "avis:r2",
                                              "etude_dossier:d1", "etude_reponse:q1", "etude_reponse:q3"}
    dates = [i["cree_le"] for i in j["items"]]
    assert dates == sorted(dates, reverse=True)
    for i in j["items"]:
        assert set(i) == {"id", "origine", "nature", "categorie", "sens", "note_sur_5", "message", "statut", "utilisateur", "cree_le", "ref"}
        assert set(i["utilisateur"]) == {"id", "email", "nom"}
    par_id = {i["id"]: i for i in j["items"]}
    a = par_id["avis:r1"]
    assert (a["origine"], a["nature"], a["note_sur_5"], a["sens"], a["message"], a["ref"]) == (
        "ancienne_version", "avis", 2, "negatif", "La mise en forme est lente", "r1")
    assert par_id["avis:r2"]["note_sur_5"] == 5 and par_id["avis:r2"]["sens"] == "positif" and par_id["avis:r2"]["message"] == ""
    n = par_id["note:t4"]
    assert (n["origine"], n["nature"], n["sens"], n["statut"], n["message"]) == ("v3", "note", "negatif", None, "Motifs : omission")
    assert par_id["note:t4"]["utilisateur"] == {"id": "prat", "email": "prat@marc.test", "nom": "Nom prat"}
    s = par_id[f"signalement:{sid}"]
    assert (s["nature"], s["categorie"], s["statut"], s["ref"]) == ("signalement", "dysfonctionnement", "ouvert", sid)
    assert par_id["etude_reponse:q1"]["categorie"] == "questionnaire_fin_etude" and par_id["etude_reponse:q1"]["origine"] == "etude"
    # filtres
    assert client.get("/v3/admin/retours?origine=ancienne_version").json()["total"] == 2
    assert client.get("/v3/admin/retours?origine=etude").json()["total"] == 3
    assert client.get("/v3/admin/retours?origine=v3").json()["total"] == 3
    assert client.get("/v3/admin/retours?statut=ouvert").json()["total"] == 1
    assert client.get("/v3/admin/retours?categorie=dysfonctionnement").json()["total"] == 1
    assert client.get("/v3/admin/retours?origine=inconnue").status_code == 422
    p = client.get("/v3/admin/retours?par_page=3&page=3").json()
    assert p["total"] == 8 and p["page"] == 3 and len(p["items"]) == 2


def test_retours_sans_doublon_ni_doublon_marque(client):
    client.en_tant_que("prat")
    sid = signaler(client).json()["id"]
    signaler(client)  # doublon : rien n'est cree
    ajouter(client, Signalement(id="dup", user_id="prat", categorie="amelioration", message="x", doublon_de=sid,
                                cree_le=datetime.now(timezone.utc)))
    client.en_tant_que("adm")
    assert [i["ref"] for i in client.get("/v3/admin/retours").json()["items"]] == [sid]


def test_extraire_avis_ne_renvoie_que_feedback():
    brut = json.dumps({"feedback": {"rating": 4, "comment": " bien "}, "corrections": [{"before": SENTINELLE}]})
    avis = retours.extraire_avis(brut)
    assert avis["note"] == 4 and avis["commentaire"] == "bien" and SENTINELLE not in repr(avis)
    assert retours.extraire_avis(None) is None and retours.extraire_avis("[]") is None
    assert retours.extraire_avis(json.dumps({"feedback": {"rating": 9}})) is None
    assert retours.extraire_avis(json.dumps({"feedback": {"rating": True, "comment": ""}})) is None
    assert len(retours.extraire_avis(json.dumps({"feedback": {"rating": 3, "comment": "a" * 5000}}))["commentaire"]) == 1000


# --------------------------------------------------------------------------- PATCH + audit chaine
def test_patch_signalement_audite_et_chaine_valide(client):
    client.en_tant_que("prat")
    sid = signaler(client).json()["id"]
    client.en_tant_que("adm")
    r = client.patch(f"/v3/admin/signalements/{sid}", json={"statut": "en_cours", "note_admin": "Reproduit en interne"})
    assert r.status_code == 200
    assert (r.json()["statut"], r.json()["note_admin"]) == ("en_cours", "Reproduit en interne")
    # inchange : pas de nouvelle entree d'audit
    assert client.patch(f"/v3/admin/signalements/{sid}", json={"statut": "en_cours"}).status_code == 200
    client.patch(f"/v3/admin/signalements/{sid}", json={"statut": "traite"})
    entrees = client.get("/v3/conformite/audit").json()["entrees"]
    sig = [e for e in entrees if e["type"] == "signalement_statut"]
    assert [e["payload"]["statut"] for e in sig] == ["en_cours", "traite"]
    assert sig[0]["acteur_id"] == "adm" and sig[0]["payload"]["note_modifiee"] is True and sig[1]["payload"]["note_modifiee"] is False
    assert "Reproduit" not in json.dumps(entrees)  # le texte de la note n'entre jamais dans la chaine
    assert client.get("/v3/conformite/audit/verification").json()["ok"] is True
    assert client.get("/v3/admin/retours?statut=traite").json()["total"] == 1


def test_patch_signalement_erreurs(client):
    client.en_tant_que("adm")
    assert client.patch("/v3/admin/signalements/inconnu", json={"statut": "traite"}).status_code == 404
    sid = "s-1"
    ajouter(client, Signalement(id=sid, user_id="prat", categorie="amelioration", message="x", cree_le=datetime.now(timezone.utc)))
    assert client.patch(f"/v3/admin/signalements/{sid}", json={}).status_code == 422
    assert client.patch(f"/v3/admin/signalements/{sid}", json={"statut": "fini"}).status_code == 422
    assert client.patch(f"/v3/admin/signalements/{sid}", json={"note_admin": "n" * 1001}).status_code == 422
    assert client.patch(f"/v3/admin/signalements/{sid}", json={"statut": "rejete"}).json()["statut"] == "rejete"


# --------------------------------------------------------------------------- utilisateurs / etude
def test_utilisateurs(client):
    _semer_ancien(client)
    ajouter(client, ConformiteHabilitation(user_id="prat", habilite=True, modifie_le="2026-01-01T00:00:00.000000Z"))
    client.en_tant_que("adm")
    j = client.get("/v3/admin/utilisateurs").json()
    par = {u["id"]: u for u in j}
    assert set(par) == {"prat", "adm", "autre"}
    assert set(par["prat"]) == {"id", "email", "nom", "role", "cree_le", "derniere_activite", "projets_v3", "comptes_rendus_anciens",
                                "dossiers_etude", "habilite_valideur"}
    assert (par["prat"]["comptes_rendus_anciens"], par["prat"]["dossiers_etude"], par["prat"]["habilite_valideur"]) == (2, 2, True)
    assert (par["adm"]["projets_v3"], par["adm"]["role"], par["adm"]["habilite_valideur"]) == (2, "admin", False)
    assert par["autre"]["comptes_rendus_anciens"] == 1 and par["autre"]["derniere_activite"]
    assert "password_hash" not in json.dumps(j)


def test_etude_reprend_la_synthese_existante(client):
    _semer_ancien(client)
    client.en_tant_que("adm")
    a = client.get("/v3/admin/etude")
    b = client.get("/admin/etude/synthese")
    assert a.status_code == 200 and a.json() == b.json()
    assert "corpus" in a.json()


# --------------------------------------------------------------------------- sante
def _controles(c):
    c.en_tant_que("adm")
    j = c.get("/v3/admin/sante").json()
    return j, {x["nom"]: x for x in j["controles"]}


def test_sante_base_saine(client):
    j, ctl = _controles(client)
    assert set(j) == {"version", "base", "controles"} and j["base"]["type"] == "sqlite"
    tables = {t["nom"]: t["lignes"] for t in j["base"]["tables"]}
    assert tables["users"] == 3 and {"reports", "signalements", "etude_dossiers", "conformite_non_conformites"} <= set(tables)
    assert ctl["orphelins"]["ok"] and ctl["doublons_comptes"]["ok"] and ctl["comptes_de_test"]["ok"]
    assert ctl["chaine_audit"]["ok"] and ctl["signalements_en_double"]["ok"] and ctl["recopie_non_conformites"]["ok"]
    assert not ctl["tables_jamais_ecrites"]["ok"] and "reports" in ctl["tables_jamais_ecrites"]["detail"]
    assert j["version"].startswith("3.")


def test_sante_detecte_les_anomalies(client):
    _semer_ancien(client)
    maintenant = datetime.now(timezone.utc)
    ajouter(
        client,
        User(id="u-maj", email="Prat@Marc.test", password_hash="x", name="Doublon casse", role="user"),
        User(id="u-test", email="essai@example.com", password_hash="x", name="Essai", role="user"),
        EtudeDossier(id="d-orphelin", session_id="session-absente", cree_a=maintenant),
        Signalement(id="g1", user_id="prat", categorie="amelioration", message="Il manque un menu", cree_le=maintenant),
        Signalement(id="g2", user_id="prat", categorie="amelioration", message="il manque un menu.", cree_le=maintenant),
        _nc("nc-x"),
    )
    j, ctl = _controles(client)
    assert not ctl["orphelins"]["ok"]
    for morceau in ("reports sans utilisateur : 1", "etude_dossiers sans session : 1"):
        assert morceau in ctl["orphelins"]["detail"]
    assert not ctl["doublons_comptes"]["ok"] and "prat@marc.test" in ctl["doublons_comptes"]["detail"]
    assert not ctl["comptes_de_test"]["ok"] and "1 compte" in ctl["comptes_de_test"]["detail"]
    assert not ctl["signalements_en_double"]["ok"] and "1 signalement" in ctl["signalements_en_double"]["detail"]
    assert not ctl["recopie_non_conformites"]["ok"]  # la NC ancienne n'est pas encore recopiee
    _recopier(client)
    assert client.get("/v3/admin/sante").json()["controles"][5]["ok"] is True


def test_sante_chaine_rompue(client):
    client.en_tant_que("adm")
    client.put("/v3/conformite/habilitations/prat", json={"habilite": True})
    client.put("/v3/conformite/habilitations/autre", json={"habilite": True})
    client.sql(lambda s: _casser(s))
    _, ctl = _controles(client)
    assert not ctl["chaine_audit"]["ok"] and "Rupture" in ctl["chaine_audit"]["detail"]


async def _casser(s):
    await s.execute(text("UPDATE conformite_audit SET payload = '{}' WHERE seq = 1"))
    await s.commit()


def test_sante_est_en_lecture_seule(client):
    _semer_ancien(client)
    avant = client.sql(_empreinte)
    client.en_tant_que("adm")
    for url in ("/v3/admin/sante", "/v3/admin/vue-ensemble?periode=tout", "/v3/admin/retours", "/v3/admin/utilisateurs"):
        assert client.get(url).status_code == 200
    assert client.sql(_empreinte) == avant


async def _empreinte(s):
    noms = ("users", "reports", "telemetrie_evenements", "etude_dossiers", "signalements", "conformite_audit")
    return [(await s.execute(text(f"SELECT COUNT(*) FROM {n}"))).scalar_one() for n in noms] + [
        (await s.execute(text("SELECT completeness_warnings FROM reports WHERE id='r1'"))).scalar_one()]
