"""Routes /v3 : SSE, ?stream=false, audio, iteration (ids conserves), export Word, sources."""
from __future__ import annotations

import io
import json

import pytest
from docx import Document
from fastapi.testclient import TestClient

import main
from auth import get_current_user
from db_models import User
from projet.llm_client import get_client_llm
from projet.referentiel import Referentiel
from projet.routes import get_referentiel, get_transcripteur
from projet.schemas import Projet
from rate_limit import limiter
from tests.test_projet_fakes import FausseKB, FauxLLM, phrase, redaction, trou

DICTEE = ("Biopsies bronchiques du lobe supérieur droit. Trois fragments de 2 mm. "
          "Prolifération tumorale d'architecture acineuse, adénocarcinome. TTF1 positif.")


def _redaction() -> dict:
    return redaction(
        phrase("macroscopie", "Trois fragments biopsiques de 2 mm.", "Trois fragments de 2 mm"),
        phrase("microscopie", "Prolifération tumorale d'architecture acineuse : adénocarcinome.",
               "Prolifération tumorale d'architecture acineuse, adénocarcinome",
               champ_id="champ:poumon.type_histologique"),
        {"section": "ihc", "type": "liste", "texte": "TTF1 : positif", "citations": ["TTF1 positif"],
         "statut": "dicte"},
        trou("ihc", "champ:poumon.pdl1", "PD-L1 (TPS)"),
        titre="EXAMEN ANATOMOPATHOLOGIQUE DE BIOPSIES BRONCHIQUES",
    )


@pytest.fixture
def faux_llm() -> FauxLLM:
    return FauxLLM(redacteur=_redaction())


@pytest.fixture
def client(faux_llm):
    app = main.app

    def _user() -> User:
        u = User()
        u.id, u.email, u.name, u.role = "u-1", "test@example.com", "Test", "user"
        return u

    async def _transcrire(octets: bytes, nom: str) -> str:
        assert octets == b"RIFF-faux-audio"
        return DICTEE

    app.dependency_overrides[get_current_user] = _user
    app.dependency_overrides[get_client_llm] = lambda: faux_llm
    app.dependency_overrides[get_referentiel] = lambda: Referentiel(FausseKB())
    app.dependency_overrides[get_transcripteur] = lambda: _transcrire
    limiter.reset()
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()
    limiter.reset()


def _evenements(texte: str) -> list[tuple[str, dict]]:
    evts = []
    for bloc in texte.strip().split("\n\n"):
        lignes = dict(l.split(": ", 1) for l in bloc.splitlines() if ": " in l)
        evts.append((lignes["event"], json.loads(lignes["data"])))
    return evts


def test_sse_etapes_puis_projet_unique(client):
    r = client.post("/v3/projets", json={"dictee": DICTEE})
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/event-stream")
    evts = _evenements(r.text)
    noms = [e for e, _ in evts]
    assert noms.count("projet") == 1 and noms[-1] == "projet"
    assert "partial" in noms and noms.index("partial") < noms.index("projet")
    steps = [d for e, d in evts if e == "step"]
    assert {s["statut"] for s in steps} >= {"en_cours", "ok"}
    p = Projet.model_validate(evts[-1][1])
    assert p.elements and p.trace


def test_stream_false_renvoie_le_projet_json(client):
    r = client.post("/v3/projets?stream=false", json={"dictee": DICTEE})
    assert r.status_code == 200
    p = Projet.model_validate(r.json())
    assert p.contexte.prelevement == "biopsie"
    assert any(e.type == "trou" and e.champ_id == "champ:poumon.pdl1" for e in p.elements)


def test_dictee_vide_400(client):
    assert client.post("/v3/projets?stream=false", json={"dictee": "   "}).status_code == 400
    assert client.post("/v3/projets?stream=false", json={"dictee": ""}).status_code == 422


def test_audio_transcrit_puis_projet(client):
    r = client.post("/v3/projets/audio?stream=false",
                    files={"audio": ("dictee.m4a", b"RIFF-faux-audio", "audio/mp4")})
    assert r.status_code == 200, r.text
    p = Projet.model_validate(r.json())
    assert p.dictee.brute == DICTEE
    t = next(t for t in p.trace if t.id == "transcription")
    assert t.statut == "ok" and "non conservé" in t.resume


def test_audio_format_refuse(client):
    r = client.post("/v3/projets/audio?stream=false", files={"audio": ("notes.txt", b"x", "text/plain")})
    assert r.status_code == 400


def test_llm_en_panne_projet_minimal_via_sse(client, faux_llm):
    from llm.base import LLMError
    for role in ("extracteur", "redacteur", "relecteur"):
        faux_llm.reponses[role] = LLMError("panne")
    evts = _evenements(client.post("/v3/projets", json={"dictee": DICTEE}).text)
    p = Projet.model_validate(evts[-1][1])
    assert evts[-1][0] == "projet" and p.contexte.niveau_service == "N3"


def test_iteration_conserve_les_ids_et_comble_le_trou(client, faux_llm):
    p = Projet.model_validate(client.post("/v3/projets?stream=false", json={"dictee": DICTEE}).json())
    trou_pdl1 = next(e for e in p.elements if e.type == "trou" and e.champ_id == "champ:poumon.pdl1")
    ids_avant = {e.id for e in p.elements if e.type != "trou"}

    def iteration(utilisateur: str) -> dict:
        assert "ELEMENTS EXISTANTS" in utilisateur and "DICTEE COMPLEMENTAIRE" in utilisateur
        existants = [dict(id=e.id, section=e.section_id, type=e.type, texte=e.texte, champ_id=e.champ_id,
                          citations=[s.extrait for s in e.sources if s.kind == "dictee"], statut="dicte")
                     for e in p.elements if e.type != "trou"]
        return redaction(*existants, {"id": trou_pdl1.id, "section": "ihc", "type": "phrase",
                                      "texte": "PD-L1 : 60 % des cellules tumorales.",
                                      "citations": ["PD-L1 60 pour cent des cellules tumorales"],
                                      "statut": "reformule", "champ_id": "champ:poumon.pdl1"},
                         titre=p.titre)

    faux_llm.reponses["redacteur"] = iteration
    r = client.post("/v3/projets/iterer?stream=false", json={
        "projet": p.model_dump(), "dictee_complementaire": "PD-L1 60 pour cent des cellules tumorales."})
    assert r.status_code == 200, r.text
    p2 = Projet.model_validate(r.json())
    assert p2.id == p.id
    assert ids_avant <= {e.id for e in p2.elements}
    comble = next(e for e in p2.elements if e.id == trou_pdl1.id)
    assert comble.type == "phrase" and "60 %" in comble.texte
    assert not any(e.type == "trou" and e.champ_id == "champ:poumon.pdl1" for e in p2.elements)
    assert p2.dictee.brute.startswith(p.dictee.brute) and "PD-L1 60" in p2.dictee.corrigee
    src = next(s for s in comble.sources if s.kind == "dictee")
    assert p2.dictee.corrigee[src.debut:src.fin].startswith("PD-L1 60")


def test_export_docx_sans_markdown_trous_rendus(client):
    p = client.post("/v3/projets?stream=false", json={"dictee": DICTEE}).json()
    r = client.post("/v3/projets/export/docx", json=p)
    assert r.status_code == 200
    doc = Document(io.BytesIO(r.content))
    texte = "\n".join(par.text for par in doc.paragraphs)
    assert "EXAMEN ANATOMOPATHOLOGIQUE" in texte
    assert "[A COMPLETER : PD-L1 (TPS)]" in texte
    assert "**" not in texte and "__" not in texte


def test_source_kb_et_source_interne(client):
    assert client.get("/v3/kb/sources/src:inca_test").json()["titre"] == "INCa test"
    assert client.get("/v3/kb/sources/src:marc_heuristiques_unites").status_code == 200
    assert client.get("/v3/kb/sources/src:inconnue").status_code == 404


def test_routes_exigent_une_authentification():
    main.app.dependency_overrides.clear()
    limiter.reset()
    with TestClient(main.app) as c:
        assert c.post("/v3/projets?stream=false", json={"dictee": DICTEE}).status_code in (401, 403)


def test_aucune_persistance_de_donnee_medicale():
    """Le paquet v3 (hors lecture de la base documentaire kb.py) n'ecrit rien : ni BDD, ni disque."""
    import pathlib
    racine = pathlib.Path(__file__).resolve().parent.parent / "projet"
    interdits = ("get_db_session", "AsyncSession", "session.add", "open(", ".write_text(", ".write_bytes(")
    for f in racine.glob("*.py"):
        if f.name == "kb.py":
            continue
        source = f.read_text(encoding="utf-8")
        for motif in interdits:
            assert motif not in source, (f.name, motif)
