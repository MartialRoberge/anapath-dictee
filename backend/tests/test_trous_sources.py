"""Preuves des trous (champ obligatoire non dicte) et sources lisibles (base reelle, LLM simule)."""
from __future__ import annotations

import asyncio
import json

import pytest
from fastapi.testclient import TestClient

import main
from auth import get_current_user
from db_models import User
from projet.orchestrateur import Pipeline
from projet.referentiel import Referentiel
from projet.routes import get_referentiel
from tests.test_projet_fakes import FauxLLM, phrase, redaction

DICTEE_SEIN = ("Microbiopsie mammaire du quadrant supéro-externe gauche. Carcinome canalaire infiltrant de grade 2 "
               "de Elston et Ellis. Récepteurs aux œstrogènes positifs à 90 %. HER2 score 1+.")


def _redaction_sein() -> dict:
    return redaction(
        phrase("microscopie", "Carcinome canalaire infiltrant de grade 2 de Elston et Ellis.",
               "Carcinome canalaire infiltrant de grade 2 de Elston et Ellis"),
        phrase("ihc", "Récepteurs aux œstrogènes positifs à 90 %.", "Récepteurs aux œstrogènes positifs à 90 %"),
        phrase("ihc", "HER2 score 1+.", "HER2 score 1+"))


@pytest.fixture(scope="module")
def ref() -> Referentiel:
    return Referentiel()


@pytest.fixture(scope="module")
def projet_sein(ref):
    return asyncio.run(Pipeline(FauxLLM(redacteur=_redaction_sein()), referentiel=ref).executer(dictee=DICTEE_SEIN))


def _ki67(p):
    return next(e for e in p.elements if e.type == "trou" and e.texte == "Ki67")


def test_trou_ki67_preuves_dans_l_ordre(projet_sein):
    e = _ki67(projet_sein)
    assert [x.categorie for x in e.preuves] == ["dictee", "regle", "referentiel"]
    dictee, regle, referentiel = e.preuves
    assert dictee.verdict == "info" and "n'est pas mentionné" in dictee.detail
    assert "ki67" in dictee.calcul.lower() and "ki 67" in dictee.calcul.lower()
    assert regle.detail == "Exigé pour : sein · biopsie · carcinome canalaire infiltrant."
    assert referentiel.source is not None and referentiel.source.libelle and referentiel.source.extrait
    assert "Ki67" in e.a_verifier and "n'a pas été dicté" in e.a_verifier
    assert e.explication == e.a_verifier


def test_trous_jamais_de_confiance_basse_ni_nom_de_fichier(projet_sein):
    trous = [e for e in projet_sein.elements if e.type == "trou"]
    assert trous
    for e in trous:
        txt = json.dumps(e.model_dump(), ensure_ascii=False).lower()
        assert "confiance basse" not in (e.explication or "").lower()
        assert ".py" not in txt and "template_" not in txt
        assert [x.categorie for x in e.preuves] == ["dictee", "regle", "referentiel"]


def _sources(obj):
    """Toutes les SourceRef d'un projet serialise."""
    if isinstance(obj, dict):
        if {"kind", "ref", "libelle"} <= obj.keys():
            yield obj
        for v in obj.values():
            yield from _sources(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _sources(v)


def test_libelles_lisibles_dans_un_projet_complet(projet_sein):
    srcs = list(_sources(projet_sein.model_dump()))
    assert srcs
    for s in srcs:
        assert len(s["libelle"]) <= 70, s["libelle"]
        assert "…" not in s["libelle"] and ".py" not in s["libelle"], s["libelle"]
        if s["extrait"]:
            assert len(s["extrait"]) <= 200 and ".py" not in s["extrait"]
        assert s["fiabilite"] in (None, "A", "B", "C", "D")


def test_libelles_lisibles_dictee_bronchique(ref):
    from tests.test_preuves import D_BB, _redaction_bb
    p = asyncio.run(Pipeline(FauxLLM(redacteur=_redaction_bb()), referentiel=ref).executer(dictee=D_BB))
    for s in _sources(p.model_dump()):
        assert len(s["libelle"]) <= 70 and "…" not in s["libelle"] and ".py" not in s["libelle"], s["libelle"]


def test_toutes_les_sources_de_la_base_ont_un_titre_court():
    from projet.kb import get_kb
    for s in get_kb().manifeste()["sources"]:
        assert s["titre_court"] and len(s["titre_court"]) <= 70 and ".py" not in s["titre_court"]
        assert s["description"]


@pytest.fixture
def client(ref):
    app = main.app

    def _user() -> User:
        u = User()
        u.id, u.email, u.name, u.role = "u-1", "test@example.com", "Test", "user"
        return u

    app.dependency_overrides[get_current_user] = _user
    app.dependency_overrides[get_referentiel] = lambda: ref
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def test_endpoint_source_forme_de_la_reponse(client):
    r = client.get("/v3/kb/sources/src:inca_donnees_minimales_2011")
    assert r.status_code == 200
    d = r.json()
    for cle in ("id", "titre_court", "titre", "description", "editeur", "version", "date_publication", "url",
                "licence", "fiabilite", "fiabilite_sens", "references"):
        assert cle in d, cle
    assert d["id"] == "src:inca_donnees_minimales_2011"
    assert d["fiabilite"] in "ABCD" and d["fiabilite_sens"]
    assert d["url"].startswith("https://")
    ref = d["references"]
    assert ref["total"] > 0 and sum(ref["par_type"].values()) == ref["total"]
    assert ref["elements"] and set(ref["elements"][0]) == {"type", "id", "libelle", "localisation"}
    assert ".py" not in json.dumps(d["references"])


def test_endpoint_source_interne_et_inconnue(client):
    d = client.get("/v3/kb/sources/src:garde_fous").json()
    assert d["titre_court"] and d["fiabilite_sens"] and d["references"] == {"total": 0, "par_type": {}, "elements": []}
    assert client.get("/v3/kb/sources/src:inconnue").status_code == 404
