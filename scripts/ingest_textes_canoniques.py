"""Ingest des TEXTES CANONIQUES du praticien (Bibles Greg.xlsx) -> JSON.

La bible Excel du pathologiste contient, par lesion, SA formulation de reference
(colonne 4) : c'est la facon dont IL redige cette lesion. On l'importe pour que
MARC puisse s'appuyer sur le vocabulaire et la structure du praticien plutot que
de produire une prose generique.

Sortie : backend/data/textes_canoniques.json
  [{ "cat", "organe", "lesion", "code", "kw": [...], "texte" }, ...]

Usage :
  python scripts/ingest_textes_canoniques.py "Ressources/1. Codes Bible/Bibles Greg.xlsx"
"""

from __future__ import annotations

import json
import re
import sys
import unicodedata
from pathlib import Path

import openpyxl  # type: ignore[import-untyped]

# Feuilles non exploitables (notes libres, brouillons).
_SKIP_SHEETS: frozenset[str] = frozenset({"Feuil1", "CR", "M"})

# Mots trop courants pour discriminer une lesion.
_STOPWORDS: frozenset[str] = frozenset({
    "de", "du", "des", "la", "le", "les", "un", "une", "et", "ou", "en", "au",
    "aux", "sur", "sans", "avec", "par", "pour", "dans", "type", "sont", "est",
    "non", "plus", "peu", "tres", "leur", "ses", "cette", "ce",
})

_MIN_TEXTE_LEN: int = 40


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFD", s).encode("ascii", "ignore").decode()
    return s.lower().strip()


def _keywords(lesion: str) -> list[str]:
    """Mots discriminants du libelle de lesion (pour le matching)."""
    tokens = re.findall(r"[a-z0-9]+", _norm(lesion))
    return [t for t in tokens if len(t) >= 4 and t not in _STOPWORDS]


def _clean_code(raw: str) -> str:
    """'DQ 4554' -> 'DQ4554' ; '7410/7332' -> '7410' (premier code)."""
    code = re.sub(r"\s+", "", raw or "")
    if "/" in code:
        code = code.split("/")[0]
    return code


def extract(xlsx_path: Path) -> list[dict[str, object]]:
    wb = openpyxl.load_workbook(str(xlsx_path), read_only=True, data_only=True)
    out: list[dict[str, object]] = []
    seen: set[tuple[str, str]] = set()
    for ws in wb.worksheets:
        if ws.title in _SKIP_SHEETS:
            continue
        for row in ws.iter_rows(values_only=True):
            cells = [str(c).strip() if c is not None else "" for c in row]
            if len(cells) < 4:
                continue
            organe, lesion, code, texte = cells[0], cells[1], cells[2], cells[3]
            if not lesion or len(texte) < _MIN_TEXTE_LEN:
                continue
            kw = _keywords(lesion)
            if not kw:
                continue
            key = (_norm(lesion), _norm(texte)[:60])
            if key in seen:  # doublon strict
                continue
            seen.add(key)
            out.append({
                "cat": ws.title,
                "organe": organe,
                "lesion": lesion,
                "code": _clean_code(code),
                "kw": kw,
                "texte": re.sub(r"[ \t]+", " ", texte).strip(),
            })
    return out


def main() -> int:
    src = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(
        "Ressources/1. Codes Bible/Bibles Greg.xlsx"
    )
    if not src.exists():
        print(f"Introuvable : {src}", file=sys.stderr)
        return 1
    entries = extract(src)
    dest = Path("backend/data/textes_canoniques.json")
    dest.parent.mkdir(parents=True, exist_ok=True)
    json.dump(entries, dest.open("w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    avec_code = sum(1 for e in entries if e["code"])
    cats = sorted({str(e["cat"]) for e in entries})
    print(f"{len(entries)} textes canoniques -> {dest}")
    print(f"  dont avec code ADICAP : {avec_code}")
    print(f"  specialites : {', '.join(cats)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
