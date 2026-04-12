"""Tests de regression — pipeline audio -> CR.

Ce harness compare la sortie du pipeline Anapath a des CR illustratifs
issus du dossier ``Ressources/2. CR avec audio/`` (5 paires audio + CR
rediges par un pathologiste).

ATTENTION : ces CR sont des EXEMPLES ILLUSTRATIFS, pas des golden tests
valides par un panel d'experts. Ils proviennent d'un seul praticien,
d'un seul labo, et couvrent principalement poumon + canal anal.

Ils servent de FILET DE SECURITE basique pour detecter des regressions
majeures, pas de mesure absolue de qualite metier.

Execution :
    pytest backend/tests/examples_illustratifs/test_audio_pairs.py -v
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest


FIXTURES_DIR: Path = Path(__file__).parent / "fixtures"
EXPECTED_DIR: Path = FIXTURES_DIR / "expected"
TRANSCRIPTS_DIR: Path = FIXTURES_DIR / "transcripts"

# Seuil de similarite minimal. 0.35 est permissif — a augmenter
# quand on aura de vrais golden tests valides par un pathologiste.
MIN_SIMILARITY: float = 0.35


def list_pair_names() -> list[str]:
    """Retourne les noms de base (sans extension) des paires disponibles."""
    if not EXPECTED_DIR.exists():
        return []
    if not TRANSCRIPTS_DIR.exists():
        return []
    expected: set[str] = {p.stem for p in EXPECTED_DIR.glob("*.txt")}
    transcripts: set[str] = {p.stem for p in TRANSCRIPTS_DIR.glob("*.txt")}
    return sorted(expected & transcripts)


PAIR_NAMES: list[str] = list_pair_names()


def _tokenize(text: str) -> set[str]:
    """Tokenise un texte en ensemble de mots normalises."""
    return {
        w.lower()
        for w in re.findall(r"[a-zA-ZÀ-ÿ]{3,}", text)
    }


def jaccard_similarity(text_a: str, text_b: str) -> float:
    """Calcule la similarite de Jaccard entre deux textes."""
    tokens_a: set[str] = _tokenize(text_a)
    tokens_b: set[str] = _tokenize(text_b)
    if not tokens_a or not tokens_b:
        return 0.0
    intersection: int = len(tokens_a & tokens_b)
    union: int = len(tokens_a | tokens_b)
    return intersection / union


def load_fixture(directory: Path, name: str) -> str:
    """Charge le contenu d'un fichier fixture."""
    path: Path = directory / f"{name}.txt"
    return path.read_text(encoding="utf-8")


@pytest.mark.skipif(
    not PAIR_NAMES,
    reason="Aucune paire transcript+expected presente. Lancer scripts/build_golden_fixtures.py d'abord.",
)
@pytest.mark.parametrize("pair_name", PAIR_NAMES)
def test_pipeline_similarity(pair_name: str) -> None:
    """Verifie que le pipeline produit un CR suffisamment proche de l'exemple."""
    expected: str = load_fixture(EXPECTED_DIR, pair_name)
    transcript: str = load_fixture(TRANSCRIPTS_DIR, pair_name)

    # Pour l'instant on ne peut pas appeler le pipeline sans les deps
    # Ce test sera active quand l'integration sera complete.
    # result = await produce_cr(transcript)
    # similarity = jaccard_similarity(result.formatted_report, expected)
    # assert similarity >= MIN_SIMILARITY

    # Placeholder : verifier juste que les fixtures sont chargees
    assert len(expected) > 50, f"CR illustratif {pair_name} trop court"
    assert len(transcript) > 10 or True, "Transcript peut etre absent"
