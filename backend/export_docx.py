"""Export de comptes-rendus anatomopathologiques au format Word (.docx).

Reproduit fidèlement le format des CR anapath de référence :
- Police : Arial 10pt
- Titre : centré, gras, souligné, majuscules
- Renseignements cliniques : italique, justifié
- Sous-titres numérotés : gras + souligné, justifié
- Labels de section (Macroscopie, L'étude histologique) : gras
- Inclusion : italique
- CONCLUSION : gras + souligné + italique pour le label, gras pour le texte
- Corps : normal, justifié
- Tableaux IHC : grille 3 colonnes
- Marqueurs [A COMPLETER: xxx] : rouge gras
"""

import io
import re

from docx import Document
from docx.shared import Pt, RGBColor, Cm
from docx.enum.text import WD_ALIGN_PARAGRAPH

_RED: RGBColor = RGBColor(220, 38, 38)
_BLACK: RGBColor = RGBColor(0, 0, 0)
_FONT_NAME: str = "Arial"
_FONT_SIZE: Pt = Pt(10)

_PATTERN_A_COMPLETER: re.Pattern[str] = re.compile(
    r"(\[A COMPLETER\s*:\s*[^\]]+\])", re.IGNORECASE
)

_PATTERN_BOLD_UNDERLINE: re.Pattern[str] = re.compile(
    r"\*\*__(.+?)__\*\*|__(.+?)__"
)

_PATTERN_INLINE: re.Pattern[str] = re.compile(
    r"(\*\*\*.+?\*\*\*|\*\*.+?\*\*|\*.+?\*)"
)


def markdown_to_docx(markdown_text: str, title: str) -> bytes:
    """Convertit un rapport Markdown en document Word au format anapath standard."""
    doc: Document = Document()

    # Style par défaut : Arial 10pt
    style = doc.styles["Normal"]
    font = style.font
    font.name = _FONT_NAME
    font.size = _FONT_SIZE

    # Marges
    for section in doc.sections:
        section.top_margin = Cm(2)
        section.bottom_margin = Cm(2)
        section.left_margin = Cm(2.5)
        section.right_margin = Cm(2.5)

    lines: list[str] = markdown_text.split("\n")
    i: int = 0

    while i < len(lines):
        line: str = lines[i]
        stripped: str = line.strip()

        # Ligne vide → paragraphe vide pour l'espacement
        if not stripped:
            p = doc.add_paragraph()
            _set_font(p, _FONT_NAME, _FONT_SIZE)
            i += 1
            continue

        # Tableau markdown
        if stripped.startswith("|") and i + 1 < len(lines):
            table_lines: list[str] = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                table_lines.append(lines[i])
                i += 1
            _add_table(doc, table_lines)
            continue

        # Titre principal : **__TEXTE__** ou ligne entièrement en MAJUSCULES gras souligné
        bu_match: re.Match[str] | None = _PATTERN_BOLD_UNDERLINE.match(stripped)
        if bu_match:
            text: str = bu_match.group(1) or bu_match.group(2) or ""
            # Détecter si c'est CONCLUSION
            is_conclusion: bool = "CONCLUSION" in text.upper()
            # Détecter si c'est le titre principal (tout en majuscules et première occurrence)
            is_titre: bool = text == text.upper() and not text.startswith(("1)", "2)", "3)", "4)", "5)"))

            p = doc.add_paragraph()
            if is_titre and not is_conclusion:
                p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            else:
                p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY

            # Texte après le pattern (ex: ":" après le titre numéroté)
            rest: str = stripped[bu_match.end():].strip()

            run = p.add_run(text)
            run.bold = True
            run.underline = True
            if is_conclusion:
                run.italic = True
            run.font.name = _FONT_NAME
            run.font.size = _FONT_SIZE
            run.font.color.rgb = _BLACK

            if rest:
                run2 = p.add_run(f" {rest}")
                run2.font.name = _FONT_NAME
                run2.font.size = _FONT_SIZE
                run2.font.color.rgb = _BLACK

            i += 1
            continue

        # Headers markdown (## Titre)
        if stripped.startswith("# "):
            p = doc.add_paragraph()
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            run = p.add_run(stripped[2:].strip().upper())
            run.bold = True
            run.underline = True
            run.font.name = _FONT_NAME
            run.font.size = _FONT_SIZE
            run.font.color.rgb = _BLACK
            i += 1
            continue
        if stripped.startswith("## ") or stripped.startswith("### "):
            level: int = 3 if stripped.startswith("### ") else 2
            text = stripped[level + 1:].strip()
            p = doc.add_paragraph()
            p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
            run = p.add_run(text)
            run.bold = True
            if level == 2:
                run.underline = True
            run.font.name = _FONT_NAME
            run.font.size = _FONT_SIZE
            run.font.color.rgb = _BLACK
            i += 1
            continue

        # Séparateur ---
        if stripped == "---":
            i += 1
            continue

        # Paragraphe normal
        p = doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
        _add_rich_text(p, stripped)
        i += 1

    buffer: io.BytesIO = io.BytesIO()
    doc.save(buffer)
    return buffer.getvalue()


def _set_font(paragraph: object, name: str, size: Pt) -> None:
    """Applique la police par défaut à un paragraphe vide."""
    run = paragraph.add_run("")  # type: ignore[union-attr]
    run.font.name = name
    run.font.size = size


def _add_rich_text(paragraph: object, text: str) -> None:
    """Parse le texte inline avec gestion du gras, italique, et [A COMPLETER]."""
    # D'abord, splitter sur les marqueurs [A COMPLETER: xxx]
    parts_completer: list[str] = _PATTERN_A_COMPLETER.split(text)

    for part_c in parts_completer:
        if not part_c:
            continue

        # Marqueur [A COMPLETER: xxx] → rouge gras
        if _PATTERN_A_COMPLETER.fullmatch(part_c):
            run = paragraph.add_run(part_c)  # type: ignore[union-attr]
            run.bold = True
            run.font.color.rgb = _RED
            run.font.name = _FONT_NAME
            run.font.size = _FONT_SIZE
            continue

        # Traiter le markdown inline
        _add_markdown_runs(paragraph, part_c)


def _add_markdown_runs(paragraph: object, text: str) -> None:
    """Parse le markdown inline en runs Word."""
    # Gérer **__TEXT__** et __TEXT__
    text = _PATTERN_BOLD_UNDERLINE.sub(
        lambda m: m.group(1) or m.group(2) or "", text
    )

    # Split sur bold/italic patterns
    pattern: re.Pattern[str] = re.compile(
        r"(\*\*\*.+?\*\*\*|\*\*.+?\*\*|\*.+?\*)"
    )
    parts: list[str] = pattern.split(text)

    for part in parts:
        if not part:
            continue

        run = paragraph.add_run("")  # type: ignore[union-attr]
        run.font.name = _FONT_NAME
        run.font.size = _FONT_SIZE
        run.font.color.rgb = _BLACK

        if part.startswith("***") and part.endswith("***"):
            run.text = part[3:-3]
            run.bold = True
            run.italic = True
        elif part.startswith("**") and part.endswith("**"):
            run.text = part[2:-2]
            run.bold = True
        elif part.startswith("*") and part.endswith("*") and len(part) > 2:
            run.text = part[1:-1]
            run.italic = True
        else:
            run.text = part


def _add_table(doc: Document, table_lines: list[str]) -> None:
    """Ajoute un tableau IHC au format anapath standard."""
    rows_data: list[list[str]] = []
    for idx, line in enumerate(table_lines):
        cells: list[str] = [c.strip() for c in line.strip().strip("|").split("|")]
        # Ignorer la ligne de séparation (---|---|---)
        if idx == 1 and all(re.match(r"^[-:]+$", c) for c in cells):
            continue
        rows_data.append(cells)

    if len(rows_data) < 1:
        return

    n_cols: int = max(len(r) for r in rows_data)
    table = doc.add_table(rows=len(rows_data), cols=n_cols)
    table.style = "Table Grid"

    for r_idx, row in enumerate(rows_data):
        for c_idx, cell_text in enumerate(row):
            if c_idx < n_cols:
                cell = table.cell(r_idx, c_idx)
                cell.text = ""
                p = cell.paragraphs[0]
                _add_rich_text(p, cell_text)
                # En-tête en gras
                if r_idx == 0:
                    for run in p.runs:
                        run.bold = True
                        run.font.name = _FONT_NAME
                        run.font.size = _FONT_SIZE


def split_report_sections(markdown_text: str) -> dict[str, str]:
    """Découpe un rapport Markdown en sections nommées."""
    lines: list[str] = markdown_text.split("\n")
    sections: dict[str, list[str]] = {}
    current_section: str = "titre"
    sections[current_section] = []

    for line in lines:
        stripped: str = line.strip()

        if not stripped:
            if current_section in sections:
                sections[current_section].append(line)
            continue

        detected_section: str | None = _detect_section_from_line(stripped)

        if detected_section and detected_section != current_section:
            current_section = detected_section
            if current_section not in sections:
                sections[current_section] = []

        if current_section not in sections:
            sections[current_section] = []
        sections[current_section].append(line)

    result: dict[str, str] = {}
    for section_name, section_lines in sections.items():
        content: str = "\n".join(section_lines).strip()
        if content:
            result[section_name] = content

    return result


def _detect_section_from_line(line: str) -> str | None:
    """Détecte si une ligne correspond au début d'une section."""
    clean_line: str = re.sub(r"[*_#|]", "", line).strip().lower()

    if re.search(r"\bconclusion\b", clean_line):
        return "conclusion"

    section_keywords: dict[str, list[str]] = {
        "renseignements_cliniques": [
            "renseignements cliniques",
            "renseignement clinique",
        ],
        "macroscopie": [
            "macroscopie",
            "examen macroscopique",
        ],
        "microscopie": [
            "microscopie",
            "etude histologique",
            "histologie",
            "etude cytologique",
            "l'etude histologique",
        ],
        "ihc": [
            "immunomarquage",
            "immunohistochimie",
        ],
        "biologie_moleculaire": [
            "biologie moleculaire",
            "biologie moléculaire",
        ],
    }

    for section_name, keywords in section_keywords.items():
        for keyword in keywords:
            if keyword in clean_line:
                return section_name

    return None
