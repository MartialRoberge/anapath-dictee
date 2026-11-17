"""CAS DE DEMONSTRATION TEMPORAIRE (poumon, adenocarcinome) : a retirer apres la demo.

Quand la dictee soumise correspond a la dictee de demonstration, MARC renvoie le projet pre-construit
``demo_cas_poumon.json`` (construit a partir d'une vraie sortie du pipeline, puis corrige) au lieu
d'appeler les modeles. Toute autre dictee suit le pipeline reel, sans changement.

- Activation : variable d'environnement ``MARC_DEMO_CAS`` ; ``"1"`` par defaut dans ce commit.
  ``MARC_DEMO_CAS=0`` desactive tout (le pipeline reel est toujours utilise).
- Retrait complet : supprimer ce fichier, ``demo_cas_poumon.json``, ``tests/test_demo_cas.py`` et les
  lignes marquees ``DEMO_CAS`` de ``projet/routes.py``.
- Rien n'est persiste. En SSE, les etapes de la trace sont rejouees (en_cours puis ok) en ~7 s.
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import unicodedata
import uuid
from collections.abc import AsyncIterator
from datetime import datetime, timezone
from difflib import SequenceMatcher
from functools import lru_cache
from pathlib import Path
from typing import Any

from projet.schemas import Projet

_FICHIER = Path(__file__).resolve().parent / "demo_cas_poumon.json"

#: Duree visee du rejeu SSE (la trace reelle dure ~10 s).
DUREE_REJEU_S = 7.0
#: Duree simulee de la transcription Voxtral quand la dictee arrive en audio.
DUREE_TRANSCRIPTION_MS = 1400

URL_OMS = "https://tumourclassification.iarc.who.int/"

#: Fiches de consultation des sources web citees par le cas (absentes de la base de connaissances).
SOURCES_WEB: dict[str, dict[str, Any]] = {
    URL_OMS: {
        "id": URL_OMS,
        "titre_court": "OMS · Classification des tumeurs thoraciques, 5e éd. (2021)",
        "titre": "WHO Classification of Tumours, Thoracic Tumours, 5th edition (2021)",
        "description": ("Classification de référence des tumeurs du poumon (IARC / OMS, collection « Blue Books »). "
                        "Elle définit l'adénocarcinome pulmonaire et ses sous-types architecturaux (lépidique, acineux, "
                        "papillaire, micropapillaire, solide) et sert de base à la déduction du diagnostic dans ce cas."),
        "editeur": "IARC / OMS",
        "version": "5e édition, 2021",
        "date_publication": "2021",
        "url": URL_OMS,
        "licence": "Copyright IARC : consultation en ligne, texte non reproduit par MARC",
        "fiabilite": "A",
        "fiabilite_sens": "Référentiel officiel publié (autorité nationale ou internationale).",
        "references": {"total": 1, "par_type": {"regle": 1}, "elements": [
            {"type": "règle", "libelle": "Déduction du diagnostic : TTF1 positif, p40 négatif, architecture glandulaire et cribriforme"}]},
    },
}


def actif() -> bool:
    return os.environ.get("MARC_DEMO_CAS", "1").strip() == "1"


def fiche_source(source_id: str) -> dict[str, Any] | None:
    """Fiche d'une source web du cas (route GET /v3/kb/sources/{id}) ; None si inconnue ou demo coupee."""
    return SOURCES_WEB.get(source_id) if actif() else None


# ---------------------------------------------------------------- reconnaissance de la dictee

def _canon(texte: str) -> str:
    """Forme comparable : casse, accents, ponctuation, espaces et variantes de transcription Voxtral."""
    t = unicodedata.normalize("NFKD", texte.lower())
    t = "".join(c for c in t if not unicodedata.combining(c)).replace("+", " pos ")
    t = re.sub(r"[^a-z0-9]+", " ", t)
    t = re.sub(r"\bttf\s?(?:1|un)\b|\bt t f\s?(?:1|un)\b", "ttf1", t)
    t = re.sub(r"\bp\s?(?:40|quarante)\b", "p40", t)
    mots = []
    for m in t.split():
        if m in {"plus", "positif", "positive", "pos"}:
            m = "pos"
        elif m in {"neg", "negatif", "negative", "moins"}:
            m = "neg"
        elif m == "quatre":
            m = "4"
        mots.append(m)
    return " ".join(mots)


@lru_cache(maxsize=1)
def _donnees() -> dict[str, Any]:
    return json.loads(_FICHIER.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def _reference() -> str:
    return _canon(_donnees()["dictee"]["brute"])


def correspond(dictee: str | None) -> bool:
    """La dictee est-elle (a la transcription pres) celle du cas de demonstration ?"""
    if not actif() or not dictee or not dictee.strip():
        return False
    c = _canon(dictee)
    return c == _reference() or SequenceMatcher(None, c, _reference()).ratio() >= 0.96


# ---------------------------------------------------------------- projet

def projet_demo(*, transcription: bool = False) -> Projet:
    """Copie du projet de demonstration avec un nouvel id et un nouvel horodatage."""
    d = json.loads(json.dumps(_donnees()))
    maintenant = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    identifiant = uuid.uuid4().hex
    d["id"] = identifiant
    if d.get("tracabilite"):
        d["tracabilite"]["id"] = identifiant
        d["tracabilite"]["horodatage_utc"] = maintenant
    if transcription:
        mots = len(d["dictee"]["brute"].split())
        for t in d["trace"]:
            if t["id"] != "transcription":
                t["debut_ms"] += DUREE_TRANSCRIPTION_MS
        t0 = d["trace"][0]
        t0.update(titre="Transcrire la dictée (Voxtral)", statut="ok", debut_ms=0, duree_ms=DUREE_TRANSCRIPTION_MS,
                  modele="voxtral-mini-latest", resume=f"{mots} mots transcrits (audio non conservé)", details=[])
        d["metriques"]["duree_totale_ms"] += DUREE_TRANSCRIPTION_MS
    return Projet.model_validate(d)


# ---------------------------------------------------------------- rejeu SSE

def _sse(evenement: str, donnees: object) -> str:
    return f"event: {evenement}\ndata: {json.dumps(donnees, ensure_ascii=False)}\n\n"


def _evenements(projet: Projet) -> list[tuple[int, str, dict[str, Any]]]:
    """(instant_ms, evenement, donnees) : chaque etape s'ouvre (en_cours) puis se ferme avec sa duree reelle."""
    evts: list[tuple[int, str, dict[str, Any]]] = []
    fin_redaction = 0
    for t in projet.trace:
        if t.statut == "saute":
            evts.append((t.debut_ms, "step", t.model_dump()))
            continue
        ouverte = t.model_copy(update={"statut": "en_cours", "duree_ms": None, "resume": "", "details": []})
        evts.append((t.debut_ms, "step", ouverte.model_dump()))
        fin = t.debut_ms + (t.duree_ms or 0)
        evts.append((fin, "step", t.model_dump()))
        if t.id in {"extraction", "redaction"}:
            fin_redaction = max(fin_redaction, fin)
    # Le brouillon (partial) arrive quand l'extraction et la redaction sont terminees.
    partial = {"elements": [e.model_dump() for e in projet.elements]}
    evts.append((fin_redaction, "partial", partial))
    evts.sort(key=lambda e: e[0])  # tri stable : ouverture avant fermeture a instant egal
    return evts


async def flux(projet: Projet) -> AsyncIterator[str]:
    """Rejoue step (en_cours puis ok), partial, puis projet, en ~DUREE_REJEU_S secondes."""
    evts = _evenements(projet)
    total = max(1, evts[-1][0])
    echelle = DUREE_REJEU_S * 1000 / total
    courant = 0
    for instant, evt, donnees in evts:
        attente = (instant - courant) * echelle / 1000
        if attente > 0:
            await asyncio.sleep(attente)
        courant = instant
        yield _sse(evt, donnees)
    await asyncio.sleep(0.15)
    yield _sse("projet", projet.model_dump())
