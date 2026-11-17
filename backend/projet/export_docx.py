"""Export Word d'un projet v3 : document propre, sans markdown.

Reprend la charte des CR de reference (export_docx.py historique) : Arial 10,
titre centre gras souligne, en-tetes de section gras, conclusion soulignee,
corps justifie. Les trous sont rendus « [A COMPLETER : libelle] » en rouge gras ;
les listes (IHC) une ligne par item. Le document est construit en memoire et
renvoye en octets : rien n'est ecrit sur disque.
"""
from __future__ import annotations

import io

from docx import Document  # type: ignore[import-untyped]
from docx.enum.text import WD_ALIGN_PARAGRAPH  # type: ignore[import-untyped]
from docx.shared import Pt, RGBColor  # type: ignore[import-untyped]

from projet.schemas import Projet

_POLICE = "Arial"
_TAILLE = Pt(10)
_ROUGE = RGBColor(220, 38, 38)
_NOIR = RGBColor(0, 0, 0)


def _run(paragraphe, texte: str, *, gras: bool = False, italique: bool = False,
         souligne: bool = False, couleur: RGBColor = _NOIR) -> None:
    r = paragraphe.add_run(texte)
    r.bold, r.italic, r.underline = gras, italique, souligne
    r.font.name = _POLICE
    r.font.size = _TAILLE
    r.font.color.rgb = couleur


def projet_vers_docx(projet: Projet) -> bytes:
    doc = Document()
    style = doc.styles["Normal"]
    style.font.name = _POLICE
    style.font.size = _TAILLE

    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    _run(p, projet.titre.upper(), gras=True, souligne=True)

    for section in sorted(projet.sections, key=lambda s: s.ordre):
        elements = [e for e in projet.elements if e.section_id == section.id]
        if not elements:
            continue
        doc.add_paragraph()
        conclusion = section.id == "conclusion"
        p = doc.add_paragraph()
        _run(p, (section.titre.upper() if conclusion else section.titre) + " :", gras=True,
             souligne=conclusion, italique=conclusion)
        for e in elements:
            if e.type == "liste":
                for ligne in [x.strip(" -•\t") for x in e.texte.splitlines() if x.strip()]:
                    p = doc.add_paragraph()
                    _run(p, "- " + ligne, gras=conclusion)
                continue
            p = doc.add_paragraph()
            p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
            if e.type == "trou":
                _run(p, f"[A COMPLETER : {e.texte}]", gras=True, couleur=_ROUGE)
            elif e.type == "titre":
                _run(p, e.texte, gras=True, souligne=True)
            else:
                _run(p, e.texte, gras=conclusion, italique=section.id == "renseignements")

    tampon = io.BytesIO()
    doc.save(tampon)
    return tampon.getvalue()
