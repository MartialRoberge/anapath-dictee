"""Retrieval BM25 sur les 94 CR reels indexes depuis Ressources/Modeles CR.

Strategie :
1. Pre-filtrer par organe classifie (reduction de l'espace de recherche).
2. Ranker les CR restants avec BM25 sur une requete concatenee
   (organe + sous_type + diagnostic_presume).
3. Retourner les top-k CR + les entrees Bibles Greg correspondantes
   pour fournir au LLM des exemples de style ET des textes standards
   par condition.

Pas d'embeddings a ce stade : pour 94 documents (500 a terme), BM25 suffit
et evite une dependance API + cold-start. Interface publique conservee
pour permettre un swap ulterieur (embeddings, ColBERT) sans changer
les appelants.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import cast

from rank_bm25 import BM25Okapi  # type: ignore[import-untyped]
from snowballstemmer import stemmer as snowball_stemmer  # type: ignore[import-untyped]

from schemas import BiblesEntry, ExampleCR, Organe, RetrievalResult
from text_utils import strip_accents


DATA_DIR: Path = Path(__file__).resolve().parent / "data"
CR_INDEX_PATH: Path = DATA_DIR / "cr_index.json"
BIBLES_INDEX_PATH: Path = DATA_DIR / "bibles_greg.json"

# Tokens trop frequents pour etre utiles au ranking (stop words domaine)
_STOPWORDS: set[str] = {
    "le", "la", "les", "un", "une", "des", "de", "du", "et", "ou",
    "a", "au", "aux", "en", "sur", "dans", "par", "pour", "avec",
    "est", "sont", "ete", "etait", "ont", "cette", "ce", "ces",
    "il", "elle", "ils", "elles", "on", "nous", "vous",
    "ne", "pas", "plus", "tres", "bien",
}


# ---------------------------------------------------------------------------
# Chargement et cache de l'index
# ---------------------------------------------------------------------------


_examples_cache: list[ExampleCR] | None = None
_bibles_cache: list[BiblesEntry] | None = None
_bm25_per_organe: dict[Organe, tuple[BM25Okapi, list[ExampleCR]]] = {}
_stemmer = snowball_stemmer("french")


def _load_json(path: Path) -> list[object]:
    """Charge un fichier JSON en liste brute ou leve si manquant."""
    if not path.exists():
        raise FileNotFoundError(
            f"Index manquant : {path}. Lancer les scripts d'ingestion d'abord."
        )
    with path.open("r", encoding="utf-8") as fh:
        data = json.load(fh)
    return cast(list[object], data)


def _load_examples() -> list[ExampleCR]:
    """Charge les CR examples en memoire (une fois)."""
    global _examples_cache
    if _examples_cache is not None:
        return _examples_cache
    raw_list: list[object] = _load_json(CR_INDEX_PATH)
    _examples_cache = [ExampleCR.model_validate(raw) for raw in raw_list]
    return _examples_cache


def _load_bibles() -> list[BiblesEntry]:
    """Charge les entrees Bibles Greg en memoire (une fois)."""
    global _bibles_cache
    if _bibles_cache is not None:
        return _bibles_cache
    raw_list: list[object] = _load_json(BIBLES_INDEX_PATH)
    _bibles_cache = [BiblesEntry.model_validate(raw) for raw in raw_list]
    return _bibles_cache


def load_index() -> tuple[list[ExampleCR], list[BiblesEntry]]:
    """API publique pour eager-load les deux index au demarrage du serveur."""
    return _load_examples(), _load_bibles()


# ---------------------------------------------------------------------------
# Tokenisation + stemming francais
# ---------------------------------------------------------------------------


def _tokenize(text: str) -> list[str]:
    """Tokenise un texte en tokens stemmes, sans stopwords, minuscules."""
    normalized: str = strip_accents(text.lower())
    tokens: list[str] = []
    current: list[str] = []
    for char in normalized:
        if char.isalnum():
            current.append(char)
        else:
            if current:
                word: str = "".join(current)
                if len(word) >= 3 and word not in _STOPWORDS:
                    tokens.append(_stemmer.stemWord(word))
                current = []
    if current:
        word = "".join(current)
        if len(word) >= 3 and word not in _STOPWORDS:
            tokens.append(_stemmer.stemWord(word))
    return tokens




# ---------------------------------------------------------------------------
# BM25 par organe (cache)
# ---------------------------------------------------------------------------


def _build_bm25_for_organe(organe: Organe) -> tuple[BM25Okapi, list[ExampleCR]]:
    """Construit un index BM25 pour un organe donne (cache apres premier appel)."""
    cached = _bm25_per_organe.get(organe)
    if cached is not None:
        return cached

    all_examples: list[ExampleCR] = _load_examples()
    subset: list[ExampleCR] = [e for e in all_examples if e.organe == organe]

    if not subset:
        # Fallback : prend tous les exemples si l'organe n'a aucun CR indexe
        subset = all_examples

    corpus: list[list[str]] = [
        _tokenize(f"{ex.titre} {ex.full_text}") for ex in subset
    ]
    bm25: BM25Okapi = BM25Okapi(corpus)

    _bm25_per_organe[organe] = (bm25, subset)
    return bm25, subset


# ---------------------------------------------------------------------------
# API publique
# ---------------------------------------------------------------------------


def retrieve_similar_cr(
    organe: Organe, query: str, top_k: int = 2
) -> list[ExampleCR]:
    """Retourne les top-k CR les plus similaires a la query pour cet organe.

    La query usuelle est ``f"{organe} {sous_type} {diagnostic_presume}"``
    construite apres classification. On pre-filtre par organe pour
    eviter le bruit inter-organes.
    """
    bm25, subset = _build_bm25_for_organe(organe)
    tokens: list[str] = _tokenize(query)

    if not tokens:
        return subset[:top_k]

    scores = bm25.get_scores(tokens)
    scored: list[tuple[ExampleCR, float]] = list(zip(subset, scores))
    scored.sort(key=lambda pair: pair[1], reverse=True)

    return [ex for ex, _score in scored[:top_k]]


def retrieve_bibles_entries(
    organe: Organe, diagnostic_query: str, top_k: int = 5
) -> list[BiblesEntry]:
    """Retourne les entrees Bibles Greg pertinentes pour l'organe + diagnostic.

    Utilise un matching simple lesion-token / query-token (pas BM25) car
    les textes Bibles sont courts et les requetes sont des labels,
    pas des phrases.
    """
    all_entries: list[BiblesEntry] = _load_bibles()
    subset: list[BiblesEntry] = [e for e in all_entries if e.organe == organe]

    query_tokens: set[str] = set(_tokenize(diagnostic_query))
    if not query_tokens:
        return subset[:top_k]

    def _score(entry: BiblesEntry) -> int:
        entry_tokens: set[str] = set(
            _tokenize(f"{entry.topographie} {entry.lesion}")
        )
        return len(query_tokens & entry_tokens)

    scored: list[tuple[BiblesEntry, int]] = [(e, _score(e)) for e in subset]
    scored.sort(key=lambda pair: pair[1], reverse=True)

    filtered: list[BiblesEntry] = [e for e, score in scored if score > 0]
    return filtered[:top_k]


def retrieve(
    organe: Organe, query: str, top_k_cr: int = 2, top_k_bibles: int = 5
) -> RetrievalResult:
    """Retrieval combine : exemples CR + entrees Bibles, packed dans un objet."""
    return RetrievalResult(
        exemples_cr=retrieve_similar_cr(organe, query, top_k=top_k_cr),
        entrees_bibles=retrieve_bibles_entries(organe, query, top_k=top_k_bibles),
    )
