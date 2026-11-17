"""Agent extracteur : organes, prelevement, contexte lesionnel, faits atomiques, mesures.

Le modele (mistral-large, JSON strict) releve ce qui est dicte et recopie une
citation pour chaque element. Ce module VERIFIE chaque citation dans la dictee
corrigee : un fait dont l'empan ne se retrouve pas mot pour mot est rejete (et
compte dans la trace). Les mesures sont en plus reperees de facon
deterministe (``mesures.py``) : le LLM ne peut ni en ajouter ni en retirer.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field

from projet.llm_client import MODELE_EXTRACTION, ClientLLM, Compteur, appel_json
from projet.mesures import Mesure, extraire_mesures
from projet.prompts import EXTRACTEUR_SYSTEME
from projet.referentiel import ChampAttendu
from projet.textes import Localisation, localiser

_CLASSES = {"biopsie", "piece_operatoire", "cytologie", "curage", "extemporane", "autre"}
_CONTEXTES = {"benin", "precancereux", "malin", "indetermine"}
_SECTIONS = {"renseignements", "macroscopie", "microscopie", "ihc", "conclusion"}


@dataclass(slots=True)
class Fait:
    texte: str
    citation: Localisation
    section: str
    negatif: bool
    champ_id: str | None


@dataclass(slots=True)
class Extraction:
    organes: list[tuple[str, Localisation]] = field(default_factory=list)
    prelevement: tuple[str, Localisation] | None = None
    contexte: tuple[str, Localisation] | None = None
    faits: list[Fait] = field(default_factory=list)
    mesures: list[Mesure] = field(default_factory=list)
    rejetes: list[str] = field(default_factory=list)
    modele: str | None = None


def _loc(citation: object, texte: str) -> Localisation | None:
    return localiser(citation, texte, tolerante=False) if isinstance(citation, str) else None


def valider_extraction(donnees: dict[str, object], dictee: str) -> Extraction:
    """Verifie chaque citation du LLM contre la dictee ; rejette ce qui n'y est pas."""
    ex = Extraction()
    for o in donnees.get("organes") or []:
        if isinstance(o, dict):
            loc = _loc(o.get("citation"), dictee)
            if loc and o.get("libelle"):
                ex.organes.append((str(o["libelle"]), loc))
    p = donnees.get("prelevement")
    if isinstance(p, dict) and p.get("classe") in _CLASSES:
        loc = _loc(p.get("citation"), dictee)
        if loc:
            ex.prelevement = (str(p["classe"]), loc)
    c = donnees.get("contexte_lesionnel")
    if isinstance(c, dict) and c.get("valeur") in _CONTEXTES:
        loc = _loc(c.get("citation"), dictee)
        if loc:
            ex.contexte = (str(c["valeur"]), loc)
    for f in donnees.get("faits") or []:
        if not isinstance(f, dict) or not f.get("texte"):
            continue
        loc = _loc(f.get("citation"), dictee)
        if loc is None:
            ex.rejetes.append(str(f.get("texte"))[:120])
            continue
        section = str(f.get("section") or "microscopie")
        ex.faits.append(Fait(
            texte=str(f["texte"]), citation=loc,
            section=section if section in _SECTIONS else "microscopie",
            negatif=bool(f.get("negatif")),
            champ_id=str(f["champ_id"]) if f.get("champ_id") else None,
        ))
    return ex


async def extraire(dictee: str, champs: list[ChampAttendu], client: ClientLLM, compteur: Compteur,
                   *, modele: str = MODELE_EXTRACTION, delai_s: float = 25.0) -> Extraction:
    """Agent complet : appel LLM + verification des empans + mesures deterministes."""
    attendus = [{"id": c.id, "libelle": c.libelle} for c in champs][:40]
    utilisateur = (
        "CHAMPS ATTENDUS :\n" + json.dumps(attendus, ensure_ascii=False)
        + "\n\nDICTEE :\n<<<\n" + dictee + "\n>>>"
    )
    donnees, reponse = await appel_json(client, compteur, etiquette="extracteur", modele=modele,
                                        systeme=EXTRACTEUR_SYSTEME, utilisateur=utilisateur,
                                        max_tokens=3000, delai_s=delai_s)
    ex = valider_extraction(donnees, dictee)
    ex.mesures = extraire_mesures(dictee)
    ex.modele = reponse.model
    return ex
