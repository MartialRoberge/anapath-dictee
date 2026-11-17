"""Calcul explicable de la confiance d'un element.

La confiance n'est pas un score opaque : c'est la somme de facteurs nommes,
restitues tels quels dans ``Element.explication``. Les seuils de presentation
viennent de ``schemas.niveau_de`` (haute >= 0,85 ; moyenne >= 0,6).

Facteurs :
1. ANCRAGE : citation retrouvée mot pour mot (0,90), par recouvrement (0,75),
   ou aucune (0,35) ;
2. STATUT : dicte (+0,03), normalise (0), reformule (-0,03) ;
3. RELECTEUR : fidele (+0,06), doute (-0,15), ajout/contresens conserve (-0,30),
   relecture indisponible (-0,05) ;
4. CORRECTIONS PHONETIQUES en amont dans l'empan : -(1 - c) x 0,5 chacune ;
5. FIABILITE des sources de la base citees : C (-0,02), D (-0,05).
"""
from __future__ import annotations

from dataclasses import dataclass

from projet.correcteur import position_corrigee
from projet.schemas import Correction, Element, SourceRef, niveau_de

BASE_ANCRAGE: dict[str | None, float] = {"exacte": 0.90, "ancrage": 0.75, None: 0.35}
BONUS_STATUT: dict[str, float] = {"dicte": 0.03, "normalise": 0.0, "reformule": -0.03, "a_completer": 0.0}
EFFET_RELECTEUR: dict[str | None, float] = {
    "fidele": 0.06, "doute": -0.15, "ajout": -0.30, "contresens": -0.30, None: -0.05,
}
_LIBELLE_RELECTEUR = {
    "fidele": "relecteur : fidèle", "doute": "relecteur : doute", "ajout": "relecteur : ajout possible",
    "contresens": "relecteur : contresens possible", None: "relecture indisponible",
}


def _fmt(x: float) -> str:
    return f"{x:+.2f}".replace(".", ",")


@dataclass(slots=True)
class Facteur:
    """Un terme de la somme de confiance : ``effet`` signe (le premier, ``ancrage``, est la base)."""

    code: str        # ancrage | statut | relecteur | phonetique | fiabilite
    libelle: str     # texte de l'explication
    effet: float
    ref: Correction | SourceRef | None = None


def decomposer(element: Element, *, ancrage: str | None, verdict: str | None,
               corrections: list[Correction], relecture_faite: bool = True) -> list[Facteur]:
    """Facteurs nommes de la confiance, dans l'ordre fixe : base d'ancrage, statut, relecteur, phonetique, fiabilite.

    ``sum(f.effet) `` borne a [0,05 ; 0,99] donne exactement la confiance affichee.
    """
    fs: list[Facteur] = []
    base = BASE_ANCRAGE.get(ancrage, 0.35)
    fs.append(Facteur("ancrage", {"exacte": "citation retrouvée mot pour mot dans la dictée",
                                  "ancrage": "passage de la dictée retrouvé par recouvrement",
                                  None: "aucun passage de la dictée ne le justifie"}[ancrage], base))
    st = BONUS_STATUT.get(element.statut, 0.0)
    if st:
        fs.append(Facteur("statut", f"{element.statut} ({_fmt(st)})", st))
    if relecture_faite or verdict is not None:
        r = EFFET_RELECTEUR.get(verdict if verdict in EFFET_RELECTEUR else None, -0.05)
    else:
        r = EFFET_RELECTEUR[None]
    fs.append(Facteur("relecteur",
                      f"{_LIBELLE_RELECTEUR.get(verdict if verdict in _LIBELLE_RELECTEUR else None)} ({_fmt(r)})", r))
    empans = [(src.debut, src.fin) for src in element.sources
              if src.kind == "dictee" and src.debut is not None and src.fin is not None]
    for c in corrections:
        if not c.appliquee or c.confiance >= 0.95:
            continue
        d = position_corrigee(c.debut, corrections)
        f = d + len(c.corrige)
        if any(d < fe and f > de for de, fe in empans):  # type: ignore[operator]
            p = (1 - c.confiance) * 0.5
            fs.append(Facteur("phonetique", f"correction phonétique « {c.original} » -> « {c.corrige} » ({_fmt(-p)})", -p, c))
    for src in element.sources:
        if src.kind == "kb" and src.fiabilite in ("C", "D"):
            p = 0.02 if src.fiabilite == "C" else 0.05
            fs.append(Facteur("fiabilite", f"source de fiabilite {src.fiabilite} ({_fmt(-p)})", -p, src))
    return fs


def borner(somme: float) -> float:
    return round(max(0.05, min(0.99, somme)), 2)


def calculer(element: Element, *, ancrage: str | None, verdict: str | None,
             corrections: list[Correction], relecture_faite: bool = True) -> tuple[float, str]:
    """Confiance [0,05 ; 0,99] et explication lisible pour un element non-trou."""
    fs = decomposer(element, ancrage=ancrage, verdict=verdict, corrections=corrections, relecture_faite=relecture_faite)
    score = 0.0
    for f in fs:
        score += f.effet
    return borner(score), "Confiance " + niveau_de(borner(score)) + " : " + " ; ".join(f.libelle for f in fs) + "."


def appliquer(element: Element, confiance: float, explication: str) -> Element:
    return element.model_copy(update={"confiance": confiance, "niveau": niveau_de(confiance),
                                      "explication": explication})
