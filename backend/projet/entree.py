"""Hygiene de l'ENTREE du pipeline : caracteres de controle, balises HTML, injection de prompt.

La dictee est une DONNEE, jamais une instruction. Ce module :
- ``assainir`` : retire les caracteres de controle (hors retour a la ligne et tabulation), les blocs
  <script>/<style> et les balises HTML (une dictee vocale n'en contient jamais), et neutralise les
  delimiteurs ``<<<`` / ``>>>`` utilises dans les prompts (meme longueur : les empans restent valides) ;
- ``detecter_injections`` : reperage deterministe des phrases qui ressemblent a une instruction adressee
  a l'assistant (« ignore tes instructions », « revele ton prompt »...). Ces passages ne sont JAMAIS
  executes : ils sont exclus de la detection d'organe/contexte et des prompts des agents, ne sont pas
  repris comme texte clinique, et sont signales au praticien (alerte de securite citant le passage).
  Une phrase clinique legitime n'a aucune raison de matcher ces motifs.
"""
from __future__ import annotations

import re

from text_utils import normaliser

_CONTROLE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f​-‏‪-‮⁦-⁩﻿]")
_BLOCS = re.compile(r"(?is)<\s*(script|style)\b.*?<\s*/\s*\1\s*>")
_BALISES = re.compile(r"</?[A-Za-z][^<>\n]{0,200}>")

#: Motifs d'injection (sur texte normalise sans accents, minuscule).
_INJECTION = [re.compile(p) for p in (
    r"\b(?:ignore|ignorez|oublie|oubliez|neglige|desobeis)\b[^.;\n]{0,40}\b(?:instructions?|consignes?|regles?|directives?|prompt)\b",
    r"\b(?:ignore|disregard|forget|override)\b[^.;\n]{0,40}\b(?:instructions?|rules|prompt)\b",
    r"\b(?:revele|reveler|affiche|donne|montre|repete|recopie|dis[- ]moi)\b[^.;\n]{0,40}\b(?:prompt|instructions?)\b",
    r"\b(?:prompt systeme|system prompt|message systeme|developer message)\b",
    r"\btu es (?:maintenant|desormais|un assistant|une ia|chatgpt)\b",
    r"\bagis comme\b|\bcomporte[- ]toi comme\b|\bfais semblant\b",
    r"\bnouvelles? (?:instructions?|consignes?)\b",
    r"\becris (?:que|dans le compte rendu que)\b[^.;\n]{0,60}\b(?:patient|diagnostic|tumeur|cancer)\b",
    r"\b(?:remplace|modifie|change)\b[^.;\n]{0,30}\b(?:diagnostic|conclusion)\b[^.;\n]{0,10}\b(?:par|en)\b",
)]

_FIN_PHRASE = re.compile(r"[^.;!?\n]+[.;!?]?")


def assainir(texte: str) -> tuple[str, list[str]]:
    """(texte propre, notes). Ne change JAMAIS le contenu clinique ; retire seulement le non-dictable."""
    notes: list[str] = []
    t = texte
    if "<<<" in t or ">>>" in t:  # d'abord : « <<<fin>>> » ne doit pas etre pris pour une balise
        t = t.replace("<<<", "‹‹‹").replace(">>>", "›››")
        notes.append("délimiteurs de prompt neutralisés")
    if _CONTROLE.search(t):
        t = _CONTROLE.sub("", t)
        notes.append("caractères de contrôle retirés")
    if _BLOCS.search(t):
        t = _BLOCS.sub(" ", t)
        notes.append("blocs de code (script/style) retirés")
    if _BALISES.search(t):
        t = _BALISES.sub(" ", t)
        notes.append("balises HTML retirées")
    return t, notes


def detecter_injections(texte: str) -> list[tuple[int, int, str]]:
    """Phrases (debut, fin, extrait) qui ressemblent a une instruction adressee a l'assistant."""
    res: list[tuple[int, int, str]] = []
    for m in _FIN_PHRASE.finditer(texte):
        brut = m.group(0)
        gauche = len(brut) - len(brut.lstrip())
        phrase = brut.strip()
        if not phrase:
            continue
        n = normaliser(phrase)
        if any(p.search(n) for p in _INJECTION):
            debut = m.start() + gauche
            res.append((debut, debut + len(phrase), phrase))
    return res


def masquer(texte: str, empans: list[tuple[int, int, str]]) -> str:
    """Remplace les empans par des espaces (longueur conservee : les offsets restent valides)."""
    if not empans:
        return texte
    sortie = list(texte)
    for debut, fin, _ in empans:
        for i in range(debut, min(fin, len(sortie))):
            if sortie[i] != "\n":
                sortie[i] = " "
    return "".join(sortie)
