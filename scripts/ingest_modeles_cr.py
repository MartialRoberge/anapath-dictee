"""Ingest one-shot du dossier Ressources/1. Codes Bible/Modeles CR.

Parse les 106 comptes-rendus reels en un index JSON consommable par le
retrieval BM25 v4. Chaque CR est normalise en ExampleCR typee avec
titre, organe devine, texte brut, section conclusion extraite et
keywords diagnostiques.

Execution :
    python scripts/ingest_modeles_cr.py

Sortie : backend/retrieval/data/cr_index.json

Convention : une fonction = une action. Aucune regex metier exotique ;
les heuristiques simples suffisent sur ce corpus a structure conventionnelle.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import TYPE_CHECKING

from docx import Document  # type: ignore[import-untyped]

REPO_ROOT: Path = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "backend"))

from schemas import ExampleCR, Organe  # noqa: E402  # pyright: ignore[reportMissingImports]

if TYPE_CHECKING:
    from docx.document import Document as DocxDocument  # type: ignore[import-untyped]


# ---------------------------------------------------------------------------
# Heuristiques de classification par mots-cles
# ---------------------------------------------------------------------------

# Chaque organe a ses tokens caracteristiques ; ordonnes par specificite
# decroissante : on matche sur le premier token trouve dans le titre.
ORGAN_KEYWORDS: dict[Organe, list[str]] = {
    "poumon": [
        "bb", "biopsie bronch", "poumon", "pulm", "lobe", "lobectomie",
        "ebus", "lba", "pleur", "bronch", "aspiration", "wedge",
        "carrefour", "paroi", "thym", "tep",
    ],
    "cardiovasculaire": [
        "anevr", "aorte", "carotide", "myocard", "coeur", "peric",
        "popl", "dissection",
    ],
    "digestif": [
        "duod", "gastr", "colique", "rectal", "ileal", "ilea", "anus",
        "anal", "estomac", "polype", "vesicule", "appendic", "biermer",
        "helicobacter", "rch", "adk dig",
    ],
    "sein": ["sein", "mamm", "galactoph"],
    "urologie": [
        "prost", "rein", "nephr", "vess", "testi", "epididy", "peni",
        "urolog",
    ],
    "gynecologie": [
        "col", "cervix", "endomet", "ovaire", "ovar", "uterus", "vulve",
        "placent", "gynec",
    ],
    "orl": [
        "amygdale", "larynx", "parotid", "thyroid", "gland salivaire",
        "pharynx", "cavite buccale", "nasale",
    ],
    "hematologie": [
        "bom", "lymphome", "lymphopath", "moelle", "leucemie", "myelome",
        "ganglion", "histiocytose",
    ],
    "dermatologie": ["peau", "cutan", "melanome", "nevus", "keratose"],
    "os_articulations": [
        "os", "articul", "arthro", "femur", "hanche", "genou", "canal carpien",
        "femoral",
    ],
    "tissus_mous": ["tissus mous", "sarcome", "lipome", "myxome", "angiol"],
    "neurologie": ["cerveau", "gliome", "meningiome", "nerf", "neurolog"],
    "ophtalmologie": ["oeil", "cornee", "chalazion"],
    "endocrinologie": ["parathyroid", "surrenal", "pancreas endocrine"],
}

# Sections conventionnelles des CR Modeles (detectees par prefixe uppercase)
SECTION_HEADERS_CONCLUSION: list[str] = [
    "CONCLUSION :", "CONCLUSION:", "CONCLUSION",
]

# Longueur minimale pour qu'un CR soit juge exploitable dans le corpus RAG
MIN_PARAGRAPH_COUNT: int = 3


# ---------------------------------------------------------------------------
# Extraction DOCX
# ---------------------------------------------------------------------------


def extract_paragraphs(docx_path: Path) -> list[str]:
    """Ouvre un .docx et retourne la liste des paragraphes non vides."""
    document: DocxDocument = Document(str(docx_path))
    result: list[str] = []
    for para in document.paragraphs:
        text: str = para.text.strip()
        if text:
            result.append(text)
    return result


def extract_titre(paragraphs: list[str]) -> str:
    """Le titre d'un CR est le premier paragraphe en ALL CAPS.

    Si le premier paragraphe n'est pas en ALL CAPS, retourne-le tel quel.
    """
    if not paragraphs:
        return ""
    first: str = paragraphs[0]
    return first


def extract_section_conclusion(paragraphs: list[str]) -> str:
    """Extrait le bloc conclusion : tout ce qui suit l'entete 'CONCLUSION'."""
    conclusion_parts: list[str] = []
    in_conclusion: bool = False

    for para in paragraphs:
        if not in_conclusion:
            if any(para.upper().startswith(h) for h in SECTION_HEADERS_CONCLUSION):
                in_conclusion = True
            continue
        conclusion_parts.append(para)

    return "\n".join(conclusion_parts)


# ---------------------------------------------------------------------------
# Classification par heuristique de titre + filename
# ---------------------------------------------------------------------------


def guess_organe(titre: str, filename: str) -> Organe:
    """Devine l'organe a partir du titre et du nom de fichier.

    Cherche les tokens les plus specifiques en premier. Fallback ``generic``
    si aucun mot-cle connu. La classification sera de toute facon refinee
    au runtime par Claude ; cet index RAG est juste un filtre pre-retrieval.
    """
    haystack: str = f"{titre} {filename}".lower()
    haystack_norm: str = _strip_accents(haystack)

    for organe, tokens in ORGAN_KEYWORDS.items():
        for token in tokens:
            if _strip_accents(token) in haystack_norm:
                return organe

    return "generic"


def _strip_accents(text: str) -> str:
    """Retire les accents francais pour simplifier le matching."""
    replacements: dict[str, str] = {
        "é": "e", "è": "e", "ê": "e", "ë": "e",
        "à": "a", "â": "a", "ä": "a",
        "î": "i", "ï": "i",
        "ô": "o", "ö": "o",
        "ù": "u", "û": "u", "ü": "u",
        "ç": "c",
    }
    result: str = text.lower()
    for accent, plain in replacements.items():
        result = result.replace(accent, plain)
    return result


def guess_sous_type(titre: str, filename: str) -> str:
    """Devine le sous-type de prelevement (biopsie, piece operatoire, ...)."""
    haystack: str = _strip_accents(f"{titre} {filename}".lower())

    if any(token in haystack for token in ["biopsie", "bb ", "fragment"]):
        return "biopsie"
    if any(token in haystack for token in ["lobectomie", "lobe ", "wedge", "resection", "piece"]):
        return "piece_operatoire"
    if "ebus" in haystack:
        return "ebus"
    if "lba" in haystack or "lavage" in haystack:
        return "lba"
    if "curetage" in haystack or "conisation" in haystack:
        return "piece_operatoire"
    return "inconnu"


# ---------------------------------------------------------------------------
# Extraction des mots-cles diagnostiques
# ---------------------------------------------------------------------------

DIAGNOSTIC_TOKENS: list[str] = [
    "adenocarcinome", "adk", "carcinome epidermoide", "ce ", "carcinoide",
    "carcinome", "sarcome", "lymphome", "hyperplasie", "dysplasie",
    "inflammatoire", "metastase", "rejet", "ain1", "ain2", "ain3",
    "infiltrant", "in situ", "adenome", "polype", "kyste", "benin",
    "malin", "tumeur", "fibrose", "necrose", "granulome",
]


def extract_diagnostic_keywords(full_text: str) -> list[str]:
    """Extrait les tokens diagnostiques presents dans le CR."""
    text_norm: str = _strip_accents(full_text.lower())
    found: list[str] = []
    for token in DIAGNOSTIC_TOKENS:
        if token in text_norm and token not in found:
            found.append(token)
    return found


# ---------------------------------------------------------------------------
# Orchestration principale
# ---------------------------------------------------------------------------


def parse_cr_file(docx_path: Path) -> ExampleCR | None:
    """Parse un .docx en ExampleCR ; None si le fichier est trop court."""
    try:
        paragraphs: list[str] = extract_paragraphs(docx_path)
    except (ValueError, OSError):
        return None

    if len(paragraphs) < MIN_PARAGRAPH_COUNT:
        return None

    titre: str = extract_titre(paragraphs)
    full_text: str = "\n".join(paragraphs)
    section_conclusion: str = extract_section_conclusion(paragraphs)

    organe: Organe = guess_organe(titre, docx_path.name)
    sous_type: str = guess_sous_type(titre, docx_path.name)
    keywords: list[str] = extract_diagnostic_keywords(full_text)

    return ExampleCR(
        filename=docx_path.name,
        organe=organe,
        sous_type_guess=sous_type,
        titre=titre,
        full_text=full_text,
        section_conclusion=section_conclusion,
        diagnostic_keywords=keywords,
    )


def ingest_modeles_cr(modeles_dir: Path) -> list[ExampleCR]:
    """Parse tous les .docx/.doc du dossier en liste d'ExampleCR."""
    examples: list[ExampleCR] = []

    for path in sorted(modeles_dir.iterdir()):
        if path.suffix.lower() not in {".docx", ".doc"}:
            continue
        # python-docx ne gere que .docx, pas .doc legacy
        if path.suffix.lower() == ".doc":
            continue
        example: ExampleCR | None = parse_cr_file(path)
        if example is not None:
            examples.append(example)

    return examples


def write_examples(examples: list[ExampleCR], output_path: Path) -> None:
    """Serialise la liste d'exemples en JSON pour commit dans le repo."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    payload: list[dict[str, object]] = [ex.model_dump() for ex in examples]
    with output_path.open("w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2)


def summarize_examples(examples: list[ExampleCR]) -> str:
    """Resume par organe pour le log."""
    counts: dict[str, int] = {}
    for example in examples:
        counts[example.organe] = counts.get(example.organe, 0) + 1
    parts: list[str] = [f"{organe}: {count}" for organe, count in sorted(counts.items())]
    return ", ".join(parts)


def main() -> None:
    """Point d'entree CLI."""
    modeles_dir: Path = (
        REPO_ROOT
        / "Ressources"
        / "1. Codes Bible"
        / "Modèles CR"
    )
    output_path: Path = (
        REPO_ROOT / "backend" / "retrieval" / "data" / "cr_index.json"
    )

    if not modeles_dir.exists():
        raise FileNotFoundError(f"Dossier source introuvable : {modeles_dir}")

    examples: list[ExampleCR] = ingest_modeles_cr(modeles_dir)
    write_examples(examples, output_path)

    print(f"[ingest_modeles_cr] {len(examples)} exemples")
    print(f"[ingest_modeles_cr] {summarize_examples(examples)}")
    print(f"[ingest_modeles_cr] ecrit : {output_path}")


if __name__ == "__main__":
    main()
