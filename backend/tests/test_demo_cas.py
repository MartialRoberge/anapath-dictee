"""Cas de demonstration temporaire (projet/demo_cas.py) : reconnaissance, validite, honnetete de l'explicabilite."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import main
from auth import get_current_user
from db_models import User
from projet import demo_cas
from projet.llm_client import get_client_llm
from projet.referentiel import Referentiel
from projet.routes import get_referentiel, get_transcripteur
from projet.schemas import Projet
from rate_limit import limiter
from tests.test_projet_fakes import FausseKB, FauxLLM

DICTEE = ("Biopsies pulmonaires, lobe supérieur droit. 4 fragments. On a une prolifération carcinomateuse infiltrante, "
          "avec des structures glandulaires irrégulières, parfois cribriformes, et des cellules cubocylindriques avec des "
          "noyaux augmentés de taille, nucléolés. Il y a aussi quelques zones solides. Pas de nécrose visible. "
          "En immuno, TTF1 + diffus, p40 neg. Ah oui, et le stroma est fibreux, avec une réaction desmoplastique.")
VARIANTE = DICTEE.replace("TTF1 + diffus", "TTF1 plus diffus").replace("p40 neg", "P40 négatif").rstrip(".").upper()


@pytest.fixture
def appels():
    return {"llm": 0, "stt": 0}


@pytest.fixture
def client(appels, monkeypatch):
    monkeypatch.setattr(demo_cas, "DUREE_REJEU_S", 0.3)
    monkeypatch.delenv("MARC_DEMO_CAS", raising=False)
    app = main.app

    class Compte(FauxLLM):
        async def completer(self, **kw):
            appels["llm"] += 1
            return await super().completer(**kw)

    async def _transcrire(octets: bytes, nom: str) -> str:
        appels["stt"] += 1
        return DICTEE

    def _user() -> User:
        u = User()
        u.id, u.email, u.name, u.role = "u-1", "test@example.com", "Test", "user"
        return u

    app.dependency_overrides[get_current_user] = _user
    app.dependency_overrides[get_client_llm] = lambda: Compte()
    app.dependency_overrides[get_referentiel] = lambda: Referentiel(FausseKB())
    app.dependency_overrides[get_transcripteur] = lambda: _transcrire
    limiter.reset()
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()
    limiter.reset()


def _evts(texte: str) -> list[tuple[str, dict]]:
    out = []
    for bloc in texte.strip().split("\n\n"):
        lignes = dict(ligne.split(": ", 1) for ligne in bloc.splitlines() if ": " in ligne)
        out.append((lignes["event"], json.loads(lignes["data"])))
    return out


def test_dictee_exacte_et_variantes_reconnues():
    assert demo_cas.correspond(DICTEE)
    assert demo_cas.correspond("  " + DICTEE.lower().replace(". ", ".  ") + " ")
    assert demo_cas.correspond(VARIANTE)
    assert not demo_cas.correspond("Biopsies pulmonaires, lobe supérieur droit. 3 fragments. Poumon normal.")
    assert not demo_cas.correspond("")


def test_route_texte_renvoie_le_cas_sans_modele(client, appels):
    r = client.post("/v3/projets?stream=false", json={"dictee": DICTEE})
    assert r.status_code == 200
    p = Projet.model_validate(r.json())
    assert p.titre == "BIOPSIES PULMONAIRES DU LOBE SUPÉRIEUR DROIT"
    assert appels["llm"] == 0
    r2 = client.post("/v3/projets?stream=false", json={"dictee": VARIANTE})
    assert r2.json()["id"] != p.id  # nouvel id a chaque appel
    assert r2.json()["tracabilite"]["horodatage_utc"]


def test_route_sse_rejoue_les_etapes(client):
    r = client.post("/v3/projets", json={"dictee": DICTEE})
    evts = _evts(r.text)
    noms = [e for e, _ in evts]
    assert noms[-1] == "projet" and noms.count("projet") == 1 and "partial" in noms
    steps = [d for e, d in evts if e == "step"]
    ouverts = {d["id"] for d in steps if d["statut"] == "en_cours"}
    fermes = {d["id"] for d in steps if d["statut"] in ("ok", "avertissement")}
    assert {"correction", "extraction", "redaction", "relecture", "codage"} <= ouverts <= fermes | {"transcription"}
    assert noms.index("partial") < noms.index("projet")


def test_route_audio_reconnue_et_transcription_une_seule_fois(client, appels):
    r = client.post("/v3/projets/audio?stream=false", files={"audio": ("d.m4a", b"x", "audio/mp4")})
    p = Projet.model_validate(r.json())
    assert next(t for t in p.trace if t.id == "transcription").statut == "ok"
    assert appels == {"llm": 0, "stt": 1}


def test_autre_dictee_suit_le_pipeline_reel(client, appels):
    r = client.post("/v3/projets?stream=false", json={"dictee": "Biopsies bronchiques. Trois fragments de 2 mm."})
    assert r.status_code == 200
    assert appels["llm"] > 0
    assert r.json()["titre"] != "BIOPSIES PULMONAIRES DU LOBE SUPÉRIEUR DROIT"


def test_variable_denv_desactive(client, appels, monkeypatch):
    monkeypatch.setenv("MARC_DEMO_CAS", "0")
    client.post("/v3/projets?stream=false", json={"dictee": DICTEE})
    assert appels["llm"] > 0
    assert demo_cas.fiche_source(demo_cas.URL_OMS) is None


# ---- contenu du projet ----

@pytest.fixture(scope="module")
def projet() -> Projet:
    return demo_cas.projet_demo()


def test_projet_valide_et_compte_rendu_attendu(projet):
    Projet.model_validate(projet.model_dump())
    textes = [e.texte for e in projet.elements]
    assert "4 carottes biopsiques parvenues fixées, mesurant de 3 à 6 mm." in textes
    assert "Adénocarcinome pulmonaire infiltrant, non mucineux." in textes
    assert "TTF1 : expression nucléaire diffuse." in textes and "p40 : absence d'expression." in textes
    assert [e.texte for e in projet.elements if e.type == "trou"] == [
        "Renseignements cliniques", "Inclusion (nombre de blocs ou cassettes, mode d'inclusion)", "Statut PD-L1 (TPS)", "ALK"]


def test_somme_des_effets_egale_la_confiance(projet):
    for e in projet.elements:
        if e.type == "trou":
            assert len(e.preuves) >= 3 and {p.categorie for p in e.preuves} >= {"dictee", "regle", "referentiel"}
            continue
        effets = [p.effet for p in e.preuves if p.effet is not None]
        assert abs(sum(effets) - e.confiance) < 0.006, e.texte
        ordre = [["dictee", "regle", "referentiel", "modele"].index(p.categorie) for p in e.preuves]
        assert ordre == sorted(ordre), e.texte


def test_elements_non_dictes_jamais_presentes_comme_dictes(projet):
    par_debut = {e.texte[:12]: e for e in projet.elements}
    mesure = par_debut["4 carottes b"]
    assert mesure.statut == "normalise" and mesure.a_verifier == "Mesure non dictée : à confirmer ou corriger avant validation."
    embole = par_debut["Il n'est pas"]
    assert embole.a_verifier == "Absence d'embole non dictée : à confirmer." and embole.niveau == "basse"
    concl = par_debut["Adénocarcino"]
    assert concl.statut != "dicte" and concl.a_verifier
    assert {p.categorie for p in concl.preuves if p.source and p.source.kind == "web"} == {"regle", "referentiel"}
    assert all(e.statut != "dicte" for e in projet.elements)  # rien n'est repris tel quel dans ce cas
    assert {a.element_ids[0] for a in projet.alertes if a.type == "securite"} == {mesure.id, embole.id, concl.id}
    assert len([a for a in projet.alertes if a.type == "manquant"]) == 4
    for a in projet.alertes:
        assert a.pourquoi and a.action and a.sources


def test_passages_de_la_dictee_et_corrections_exacts(projet):
    corr = projet.dictee.corrigee
    for e in projet.elements:
        for s in [*e.sources, *(p.source for p in e.preuves if p.source)]:
            if s.kind == "dictee":
                assert corr[s.debut:s.fin] == s.extrait, (e.texte, s.extrait)
    for c in projet.corrections:
        assert projet.dictee.brute[c.debut:c.fin] == c.original and c.corrige in corr and c.candidats
    assert [(c.original, c.corrige) for c in projet.corrections] == [("TTF1 +", "TTF1 positif"), ("p40 neg", "p40 négatif")]


def test_sources_resolues_et_libelles_propres(projet):
    ref = Referentiel()
    vus = set()
    for e in projet.elements:
        for s in [*e.sources, *(p.source for p in e.preuves if p.source)]:
            vus.add((s.kind, s.ref, s.libelle))
    for c in projet.codes:
        vus |= {(s.kind, s.ref, s.libelle) for s in c.sources}
    for a in projet.alertes:
        vus |= {(s.kind, s.ref, s.libelle) for s in a.sources}
    for kind, ref_id, libelle in vus:
        assert "…" not in libelle and ".py" not in libelle
        if kind in ("kb", "regle"):
            d = ref.source_detail(ref_id)
            assert d and d["titre_court"] == libelle, ref_id
        elif kind == "web":
            assert demo_cas.fiche_source(ref_id)["titre_court"] == libelle


def test_codes_existent_dans_la_base(projet):
    kb = Path(__file__).resolve().parents[1] / "kb"
    thesaurus = {c[1] for c in json.loads((kb / "adicap_thesaurus.json").read_text())["concepts"]}
    snomed = {c["concept_id"] for c in json.loads((kb / "snomed.json").read_text())["concepts"]}
    for c in projet.codes:
        if c.systeme == "ADICAP":
            assert c.code[:2] in {"BI", "BH", "PH", "PI"} and c.code[2:4] == "RP" and c.code[4:] in thesaurus
        else:
            assert c.code in snomed
