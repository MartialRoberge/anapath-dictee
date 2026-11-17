"""Agent relecteur : fidelite de chaque element contre la dictee (modele DIFFERENT du redacteur).

Le verdict du modele (mistral-medium) est croise avec l'ancrage deterministe
(etude/ancrage.py) :
- « ajout » ou « contresens » + passage introuvable dans la dictee -> RETRAIT
  et alerte securite bloquante ;
- « ajout » ou « contresens » mais element bien ancre -> conserve, confiance
  basse, alerte securite « attention » (le praticien tranche) ;
- « doute » -> confiance abaissee ; « fidele » -> confiance relevee.
Le relecteur ne reecrit jamais rien.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

from etude.ancrage import _correspond, decouper, jetons_discriminants
from projet.llm_client import MODELE_RELECTURE, ClientLLM, Compteur, appel_json
from projet.prompts import RELECTEUR_SYSTEME
from projet.schemas import Alerte, Element, SourceRef
from projet.textes import contient_terme, extrait_court, localiser
from text_utils import normaliser
from projet.mesures import chiffrer
from projet.verificateurs import Decision
from reports.numbers import chiffres_non_dictes, source_number_set

if TYPE_CHECKING:
    from projet.referentiel import Referentiel

VERDICTS = {"fidele", "ajout", "contresens", "doute"}


@dataclass(slots=True)
class Verdict:
    id: str
    verdict: str
    passage: str | None
    justification: str


async def relire(elements: list[Element], dictee: str, client: ClientLLM, compteur: Compteur,
                 *, modele: str = MODELE_RELECTURE, delai_s: float = 20.0) -> dict[str, Verdict]:
    a_relire = [{"id": e.id, "type": e.type, "texte": e.texte} for e in elements if e.type != "trou"]
    if not a_relire:
        return {}
    utilisateur = ("Dictee :\n<<<\n" + dictee + "\n>>>\n\nELEMENTS DU PROJET :\n"
                   + json.dumps(a_relire, ensure_ascii=False))
    donnees, _ = await appel_json(client, compteur, etiquette="relecteur", modele=modele,
                                  systeme=RELECTEUR_SYSTEME, utilisateur=utilisateur,
                                  max_tokens=2500, delai_s=delai_s)
    res: dict[str, Verdict] = {}
    for v in donnees.get("verdicts") or []:
        if not isinstance(v, dict):
            continue
        verdict = str(v.get("verdict") or "doute")
        res[str(v.get("id"))] = Verdict(
            id=str(v.get("id")), verdict=verdict if verdict in VERDICTS else "doute",
            passage=str(v["passage"]) if v.get("passage") else None,
            justification=str(v.get("justification") or "")[:240],
        )
    return res


def _racine(f: str) -> str:
    return re.sub(r"(?:ees|ee|es|e|s|x)$", "", f) if len(f) >= 5 else f


def _present(jeton: str, formes: list[str]) -> bool:
    """Le jeton figure-t-il dans la dictee, a l'accord pres (« droit » / « droite », « envahi » / « envahis ») ?"""
    r = _racine(jeton)
    return any(_correspond(jeton, f) or (len(r) >= 4 and r == _racine(f)) for f in formes)


#: Verbes et cadres de redaction (« Il s'agit d'un », « On observe ») : jamais un fait ajoute.
_CADRES_REDACTIONNELS = frozenset({"agit", "observe", "observon", "existe", "note", "constate", "retrouve", "correspond",
                                   "comporte", "montre", "examen", "aspect"})

#: Abreviations de dictee et leur forme normalisee (jamais une information en plus).
_ABREVIATIONS: dict[str, tuple[str, ...]] = {"adk": ("adenocarcinome",), "cis": ("situ",), "k": ("carcinome",)}


def _normalisation_legitime(jeton: str, dictee: str, ref: "Referentiel | None") -> bool:
    """Le jeton absent de la dictee est-il une NORMALISATION fidele d'un terme dicte ?

    - organe : « bronchiques » dicte -> « poumon » ecrit (meme organe selon la base) ;
    - sigle developpe : « ADK » dicte -> « adenocarcinome », « LBA » -> « lavage broncho-alveolaire ».
    Un ajout reel (un terme que rien dans la dictee ne justifie) n'est JAMAIS excuse.
    """
    norm = normaliser(dictee)
    for abrev, formes in _ABREVIATIONS.items():
        if jeton in formes and contient_terme(norm, abrev):
            return True
    if re.fullmatch(r"[ivxl]+", jeton):  # « segment sept » dicte -> « segment VII » ecrit
        valeurs = {"i": 1, "v": 5, "x": 10, "l": 50}
        n = 0
        for a, b in zip(jeton, jeton[1:] + " "):
            n += -valeurs[a] if b != " " and valeurs[b] > valeurs[a] else valeurs[a]
        if str(n) in source_number_set(dictee + "\n" + chiffrer(dictee)):
            return True
    if ref is None:
        return False
    try:
        organes_dictee = {o.id for o in ref.detecter_organes(dictee)}
        if organes_dictee and {o.id for o in ref.detecter_organes(jeton)} & organes_dictee:
            return True
        for e in ref._kb_appel("lexique", defaut=[]) or []:
            expansion = normaliser(str(e.get("expansion") or ""))
            if not expansion or jeton not in re.findall(r"[a-z0-9]+", expansion):
                continue
            sigles = [str(e.get("terme") or "")] + [str(v) for v in e.get("variantes") or [] if isinstance(v, str)]
            if any(contient_terme(norm, normaliser(x)) for x in sigles if x.strip()):
                return True
    except Exception:  # noqa: BLE001 - sans base, on reste strict : le passage sera juge non dicte
        return False
    return False


def normalisation_seule(passage: str, dictee: str, ref: "Referentiel | None" = None) -> bool:
    """Tout ce qui manque a la dictee dans le passage est une normalisation legitime (aucun ajout reel)."""
    if chiffres_non_dictes(passage, dictee + "\n" + chiffrer(dictee)) or localiser(passage, dictee, tolerante=True) is not None:
        return False
    formes = [j.forme for j in decouper(dictee)]
    attendus = [t for t in jetons_discriminants(passage) if t not in _CADRES_REDACTIONNELS]
    if not attendus:
        return True  # passage sans mot porteur (« Il s'agit d'un ») : formule redactionnelle, pas un ajout
    absents = [t for t in attendus if not _present(t, formes)]
    return bool(absents) and all(_normalisation_legitime(t, dictee, ref) for t in absents)


def passage_non_dicte(passage: str, dictee: str, ref: "Referentiel | None" = None) -> bool:
    """Le passage signale est-il absent de la dictee (deterministe) ?

    Les normalisations legitimes (organe, sigle developpe) ne comptent pas comme absentes ;
    les chiffres, eux, doivent TOUJOURS etre dictes.
    """
    if chiffres_non_dictes(passage, dictee + "\n" + chiffrer(dictee)):
        return True
    if localiser(passage, dictee, tolerante=True) is not None:
        return False
    formes = [j.forme for j in decouper(dictee)]
    attendus = jetons_discriminants(passage)
    absents = [t for t in attendus if not _present(t, formes)]
    return any(not _normalisation_legitime(t, dictee, ref) for t in absents)


def decider(elements: list[Element], verdicts: dict[str, Verdict], dictee: str, modele: str,
            ref: "Referentiel | None" = None) -> Decision:
    d = Decision()
    src = SourceRef(kind="agent", ref=f"relecteur:{modele}", libelle=f"Relecteur ({modele})")
    n = 0
    ignores = 0
    for e in elements:
        v = verdicts.get(e.id)
        if e.type == "trou" or v is None or v.verdict not in ("ajout", "contresens"):
            continue
        if normalisation_seule(v.passage or e.texte, dictee, ref):
            ignores += 1  # « bronchiques » -> « poumon » : terminologie normalisee, pas un ajout
            continue
        n += 1
        ancre = any(s.kind == "dictee" for s in e.sources)
        passage = v.passage or e.texte
        confirme = passage_non_dicte(passage, dictee, ref)
        if confirme or not ancre:
            d.retraits[e.id] = f"relecteur : {v.verdict} ({v.justification or passage})"
            d.alertes.append(Alerte(
                id=f"r{n}", type="securite", gravite="bloquant",
                message=(f"Élément retiré : « {extrait_court(e.texte, 140)} » contient un {v.verdict} "
                         f"non retrouvé dans la dictée ({extrait_court(passage, 80)})."),
                element_ids=[e.id], confiance=0.85, sources=[src], agent="Relecteur",
                pourquoi=(f"Le modèle relecteur a signalé un {v.verdict} et le contrôle automatique confirme que ce passage "
                          "n'est pas dans la dictée : l'élément est retiré."),
                action="Vérifier que le passage dicté repris à la place convient"))
        else:
            d.alertes.append(Alerte(
                id=f"r{n}", type="securite", gravite="attention",
                message=f"À vérifier : le relecteur signale un possible {v.verdict} - {v.justification or passage}.",
                element_ids=[e.id], suggestion=f"Comparer « {extrait_court(passage, 80)} » à la dictée",
                confiance=0.6, sources=[src], agent="Relecteur",
                pourquoi=(f"Le modèle relecteur signale un possible {v.verdict}, mais le passage reste retrouvé dans la dictée : "
                          "à vous de trancher."),
                action="Comparer le passage à la dictée et corriger si besoin"))
    d.details.append(f"{sum(1 for v in verdicts.values() if v.verdict == 'fidele')} fidèle(s), "
                     f"{len(d.retraits)} retrait(s), {n - len(d.retraits)} signalement(s)"
                     + (f", {ignores} normalisation(s) légitime(s) conservée(s)" if ignores else ""))
    return d
