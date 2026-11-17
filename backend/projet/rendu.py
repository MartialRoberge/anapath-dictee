"""Rendu texte d'un projet (pour les verificateurs historiques, le codeur et l'export).

Deux formes :
- ``rendu_controle`` : texte au format attendu par ``reports/coherence_document.py``
  (titre ``**__TITRE__**``, en-tetes ``**Macroscopie :**``), avec la position de
  chaque element pour rattacher une alerte a l'element fautif ;
- ``rendu_texte`` : texte brut lisible (codeur ADICAP/SNOMED, export).
Les trous sont rendus ``[A COMPLETER : libelle]`` : ils ne sont jamais du contenu affirme.
"""
from __future__ import annotations

from projet.schemas import Element, Section


def texte_element(e: Element) -> str:
    if e.type == "trou":
        return f"[A COMPLETER : {e.texte}]"
    return e.texte


def rendu_controle(titre: str, sections: list[Section], elements: list[Element]) -> tuple[str, dict[str, tuple[int, int]]]:
    """Texte + positions {element_id: (debut, fin)} dans ce texte."""
    morceaux: list[str] = [f"**__{titre}__**\n"]
    longueur = len(morceaux[0])
    positions: dict[str, tuple[int, int]] = {}
    for s in sorted(sections, key=lambda s: s.ordre):
        els = [e for e in elements if e.section_id == s.id]
        if not els:
            continue
        entete = f"**{s.titre} :**\n" if s.id != "conclusion" else "**__CONCLUSION :__**\n"
        morceaux.append(entete)
        longueur += len(entete)
        for e in els:
            t = texte_element(e)
            positions[e.id] = (longueur, longueur + len(t))
            morceaux.append(t + "\n")
            longueur += len(t) + 1
    return "".join(morceaux), positions


def rendu_texte(titre: str, sections: list[Section], elements: list[Element]) -> str:
    lignes: list[str] = [titre, ""]
    for s in sorted(sections, key=lambda s: s.ordre):
        els = [e for e in elements if e.section_id == s.id]
        if not els:
            continue
        lignes.append(s.titre.upper() if s.id == "conclusion" else s.titre)
        lignes.extend(texte_element(e) for e in els)
        lignes.append("")
    return "\n".join(lignes).strip()


def elements_touches(positions: dict[str, tuple[int, int]], debut: int, fin: int) -> list[str]:
    return [eid for eid, (d, f) in positions.items() if debut < f and fin > d]
