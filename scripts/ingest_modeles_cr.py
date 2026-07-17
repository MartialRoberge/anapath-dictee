"""Ingest des MODELES CR du praticien (raccourcis -> texte long) -> formulations.

Les fichiers de ``Ressources/1. Codes Bible/Modeles CR`` ne sont PAS des comptes
rendus complets : ce sont les RACCOURCIS que le praticien utilise pour saisir un
texte recurrent. Le NOM DU FICHIER est le raccourci ("BB Kepi" = Biopsie
Bronchique + carcinome epidermoide), le CONTENU est le texte a produire.

Ils sont ~85% thoraciques, la ou la bible Excel n'a que 9 entrees THO : ils
comblent donc exactement le trou du catalogue de formulations, via le meme
mecanisme (reports/canonical_texts.py). Aucune architecture nouvelle.

Usage :
  python scripts/ingest_modeles_cr.py "Ressources/1. Codes Bible/Modeles CR"
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
import unicodedata
from pathlib import Path

# Prefixe du raccourci -> (chapitre de bible, organe, libelle du prelevement).
# Le chapitre/organe doivent correspondre a reports/canonical_texts._ORGAN_TO_CATALOG.
_PREFIXES: dict[str, tuple[str, str, str]] = {
    "BB": ("THO", "Poumon", "biopsie bronchique"),
    "BTB": ("THO", "Poumon", "biopsie transbronchique"),
    "EBUS": ("THO", "Poumon", "cytoponction ganglionnaire transbronchique (EBUS)"),
    "LOBE": ("THO", "Poumon", "lobectomie"),
    "PSS": ("THO", "Poumon", "ponction biopsie d'un nodule pulmonaire"),
    "TEP": ("THO", "Poumon", "biopsie pulmonaire"),
    "TEP1": ("THO", "Poumon", "biopsie pulmonaire"),
    "TEP2": ("THO", "Poumon", "biopsie pulmonaire"),
    "PLEVRE": ("THO", "Poumon", "biopsie pleurale"),
    "LIQ": ("THO", "Poumon", "liquide"),
    "THYMOME": ("THO", "Poumon", "thymome"),
}

# Suffixe du raccourci -> lesion en clair (sert aux mots-cles de recherche).
_LESIONS: tuple[tuple[str, str], ...] = (
    ("kgc", "carcinome a grandes cellules"),
    ("k ptes cell", "carcinome a petites cellules"),
    ("k petites cell", "carcinome a petites cellules"),
    ("kepi", "carcinome epidermoide"),
    ("adk", "adenocarcinome"),
    ("carcinoide", "tumeur carcinoide"),
    ("kgv", "carcinome"),
    ("mdh", "maladie de hodgkin"),
    ("histiocytose", "histiocytose"),
    ("tuberculose", "tuberculose"),
    ("inflamm", "inflammatoire"),
    ("normal", "normal"),
    ("sain", "sain"),
    ("anthracosique", "anthracosique"),
)

_STOP: frozenset[str] = frozenset({
    "avec", "sans", "dans", "pour", "les", "des", "une", "por", "sur", "docx", "doc",
})


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFD", s).encode("ascii", "ignore").decode()
    return s.lower().strip()


def _docx_text(path: Path) -> str:
    out = subprocess.run(
        ["textutil", "-convert", "txt", "-stdout", str(path)],
        capture_output=True, text=True, check=False,
    )
    return re.sub(r"\n{3,}", "\n\n", out.stdout).strip()


def _decode(stem: str) -> tuple[str, str, str] | None:
    """Raccourci -> (chapitre, organe, libelle de lesion). None si hors perimetre."""
    prefix = stem.split()[0].upper() if stem.split() else ""
    meta = _PREFIXES.get(prefix)
    if meta is None:
        return None
    cat, organe, prelevement = meta
    low = _norm(stem)
    lesion_terms = [clair for court, clair in _LESIONS if court in low]
    lesion = f"{prelevement} — {lesion_terms[0]}" if lesion_terms else prelevement
    return cat, organe, lesion


def _keywords(stem: str, texte: str) -> list[str]:
    """Mots-cles de recherche : le prelevement + la lesion decodee + le titre du doc."""
    decoded = _decode(stem)
    base = decoded[2] if decoded else ""
    titre = texte.split("\n")[0] if texte else ""
    tokens = re.findall(r"[a-z0-9]+", _norm(f"{base} {titre}"))
    seen: list[str] = []
    for t in tokens:
        if len(t) >= 4 and t not in _STOP and t not in seen:
            seen.append(t)
    return seen[:12]


def main() -> int:
    src = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(
        "Ressources/1. Codes Bible/Modèles CR"
    )
    if not src.is_dir():
        print(f"Introuvable : {src}", file=sys.stderr)
        return 1
    dest = Path("backend/data/textes_canoniques.json")
    catalog: list[dict[str, object]] = json.loads(dest.read_text(encoding="utf-8"))
    before = len(catalog)
    # Purge d'un import precedent (idempotent).
    catalog = [e for e in catalog if e.get("source") != "modeles_cr"]

    added = 0
    for path in sorted(src.iterdir()):
        if path.suffix.lower() not in (".doc", ".docx"):
            continue
        decoded = _decode(path.stem)
        if decoded is None:
            continue  # hors perimetre (digestif/CV : deja couverts par la bible Excel)
        cat, organe, lesion = decoded
        texte = _docx_text(path)
        if len(texte) < 80:
            continue
        kw = _keywords(path.stem, texte)
        if not kw:
            continue
        catalog.append({
            "cat": cat, "organe": organe, "lesion": lesion, "code": "",
            "kw": kw, "texte": re.sub(r"[ \t]+", " ", texte)[:900],
            "source": "modeles_cr", "raccourci": path.stem,
        })
        added += 1

    dest.write_text(
        json.dumps(catalog, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    tho = sum(1 for e in catalog if e.get("cat") == "THO")
    print(f"{added} modeles CR thoraciques ingeres")
    print(f"  catalogue : {before} -> {len(catalog)} formulations")
    print(f"  chapitre THO : {tho} entrees (etait 9)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
