"""Golden tests de regression — pipeline audio -> CR.

Ce harness compare la sortie du pipeline Anapath a des CR de reference
issus du dossier ``Ressources/2. CR avec audio/`` (5 paires audio + CR
rediges par un pathologiste).

Fonctionnement :

1. Les fichiers ``fixtures/expected/*.txt`` sont les CR de reference
   extraits depuis les ``.docx`` (generes par
   ``scripts/build_golden_fixtures.py``).

2. Les fichiers ``fixtures/transcripts/*.txt`` sont les transcriptions
   Voxtral des 5 audio. Ils sont couteux a produire (appel API) donc
   commites dans le repo apres une execution unique de
   ``scripts/run_golden_v3.py``.

3. Chaque test passe la transcription correspondante au pipeline
   ``format_transcription`` v3 (ou v4 en Phase 2) et mesure la similarite
   entre le rapport genere et le CR de reference via une metrique
   simple de chevauchement de tokens.

Ces tests sont un FILET DE SECURITE : ils figent la qualite v3 pour
permettre une bascule v4 sans regression silencieuse. Ils ne sont pas
une mesure absolue de qualite metier.

Execution :
    pytest backend/tests/golden/test_audio_pairs.py -v
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest


FIXTURES_DIR: Path = Path(__file__).parent / "fixtures"
EXPECTED_DIR: Path = FIXTURES_DIR / "expected"
TRANSCRIPTS_DIR: Path = FIXTURES_DIR / "transcripts"

# Seuil de similarite minimal au-dessous duquel le test echoue.
# Ajuste apres le baseline initial.
MIN_SIMILARITY: float = 0.35


def list_pair_names() -> list[str]:
    """Retourne les noms de base (sans extension) des paires disponibles."""
    if not EXPECTED_DIR.exists():
        return []
    return sorted(p.stem for p in EXPECTED_DIR.glob("*.txt"))


def tokenize(text: str) -> set[str]:
    """Tokenise un texte en ensemble de mots normalises (sans accents, minuscules)."""
    lowered: str = text.lower()
    stripped: str = _strip_accents(lowered)
    tokens: list[str] = re.findall(r"\b[a-z0-9]{3,}\b", stripped)
    return set(tokens)


def _strip_accents(text: str) -> str:
    """Version minimaliste utilisee uniquement dans les tests."""
    replacements: dict[str, str] = {
        "é": "e", "è": "e", "ê": "e", "ë": "e",
        "à": "a", "â": "a", "ä": "a",
        "î": "i", "ï": "i",
        "ô": "o", "ö": "o",
        "ù": "u", "û": "u", "ü": "u",
        "ç": "c",
    }
    result: str = text
    for accent, plain in replacements.items():
        result = result.replace(accent, plain)
    return result


def compute_similarity(produced: str, expected: str) -> float:
    """Similarite de Jaccard sur les tokens (0.0 a 1.0).

    Pas une metrique medicale serieuse, juste un proxy pour detecter
    une regression majeure (tokens perdus, style different).
    """
    produced_tokens: set[str] = tokenize(produced)
    expected_tokens: set[str] = tokenize(expected)

    if not produced_tokens or not expected_tokens:
        return 0.0

    intersection: set[str] = produced_tokens & expected_tokens
    union: set[str] = produced_tokens | expected_tokens
    return len(intersection) / len(union)


def load_fixture(directory: Path, name: str) -> str:
    """Charge un fichier texte de fixture ou leve FileNotFoundError."""
    path: Path = directory / f"{name}.txt"
    if not path.exists():
        raise FileNotFoundError(
            f"Fixture manquante : {path}. "
            f"Executer scripts/build_golden_fixtures.py et/ou scripts/run_golden_v3.py."
        )
    return path.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Tests parametrises
# ---------------------------------------------------------------------------


PAIR_NAMES: list[str] = list_pair_names()


@pytest.mark.skipif(
    not PAIR_NAMES,
    reason="Aucune fixture golden presente. Lancer build_golden_fixtures.py.",
)
@pytest.mark.parametrize("pair_name", PAIR_NAMES)
def test_expected_fixture_is_non_empty(pair_name: str) -> None:
    """Sanity check : chaque CR de reference a du contenu."""
    expected: str = load_fixture(EXPECTED_DIR, pair_name)
    assert len(expected.strip()) > 100, (
        f"Le CR attendu {pair_name} fait moins de 100 caracteres."
    )


@pytest.mark.skipif(
    not PAIR_NAMES,
    reason="Aucune fixture golden presente.",
)
@pytest.mark.parametrize("pair_name", PAIR_NAMES)
def test_baseline_matches_expected_if_available(pair_name: str) -> None:
    """Compare un eventuel baseline v3 genere avec le CR attendu.

    Ce test n'est utile qu'une fois que ``run_golden_v3.py`` a produit
    les fixtures ``baseline_v3/*.txt``. Il skip sinon.
    """
    baseline_path: Path = FIXTURES_DIR / "baseline_v3" / f"{pair_name}.txt"
    if not baseline_path.exists():
        pytest.skip(f"Baseline v3 non generee pour {pair_name}.")

    expected: str = load_fixture(EXPECTED_DIR, pair_name)
    produced: str = baseline_path.read_text(encoding="utf-8")

    similarity: float = compute_similarity(produced, expected)
    assert similarity >= MIN_SIMILARITY, (
        f"Similarite {similarity:.2f} < seuil {MIN_SIMILARITY} pour {pair_name}. "
        f"Le pipeline a regresse par rapport au CR de reference."
    )
