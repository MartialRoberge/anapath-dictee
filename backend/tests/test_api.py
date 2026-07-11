"""Tests d'API (FastAPI TestClient) avec moteur et auth remplaces."""

import pytest
from fastapi.testclient import TestClient

import main
from auth import get_current_user
from db_models import User
from reports.factory import get_report_engine
from tests.conftest import FakeEngine, make_report


@pytest.fixture
def client():
    app = main.app

    def _fake_user() -> User:
        u = User()
        u.id = "u-1"
        u.email = "test@example.com"
        u.name = "Test"
        u.role = "user"
        return u

    engine = FakeEngine(report=make_report())
    app.dependency_overrides[get_current_user] = _fake_user
    app.dependency_overrides[get_report_engine] = lambda: engine
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_format_returns_report(client):
    r = client.post("/format", json={"raw_text": "biopsie pulmonaire adk"})
    assert r.status_code == 200
    body = r.json()
    assert body["organe_detecte"] == "poumon"
    assert body["organes_detectes"] == ["poumon"]
    assert body["type_prelevement"] == "biopsie"
    assert "formatted_report" in body
    assert isinstance(body["warnings"], list)


def test_format_empty_text_400(client):
    r = client.post("/format", json={"raw_text": "   "})
    assert r.status_code == 400


def test_iterate_returns_report(client):
    r = client.post(
        "/iterate",
        json={"rapport_actuel": "CR existant", "nouveau_transcript": "ajout ALK-"},
    )
    assert r.status_code == 200
    assert r.json()["organe_detecte"] == "poumon"


def test_iterate_empty_400(client):
    r = client.post(
        "/iterate", json={"rapport_actuel": "", "nouveau_transcript": "x"}
    )
    assert r.status_code == 400


def test_sections_endpoint(client):
    cr = "**__TITRE__**\n**Macroscopie :**\nx\n**__CONCLUSION :__**\n**y**"
    r = client.post("/sections", json={"formatted_report": cr})
    assert r.status_code == 200
    assert isinstance(r.json()["sections"], dict)


def test_warnings_propagated(client):
    app = main.app
    engine = FakeEngine(
        report=make_report(warnings=["Mesure '42 mm' absente de la dictee : a verifier."])
    )
    app.dependency_overrides[get_report_engine] = lambda: engine
    r = client.post("/format", json={"raw_text": "biopsie"})
    assert any("42" in w for w in r.json()["warnings"])
