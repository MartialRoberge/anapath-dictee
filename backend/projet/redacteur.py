"""Agent redacteur : sections + elements (phrase/titre/liste/trou) au style CR ACP francais.

Le modele (mistral-large) redige et recopie, pour chaque element, les passages
de dictee qui le justifient. Ce module :
- retrouve chaque citation dans la dictee corrigee (empan calcule ici) ;
- normalise les sections sur le gabarit ;
- nettoie tout residu de markdown ;
- garantit les trous : seuls les champs fournis peuvent devenir des trous.

En repli (LLM indisponible), ``projet_minimal`` produit un projet FIDELE a la
dictee, phrase par phrase, sans aucune reformulation (niveau de service N3).
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

from projet.llm_client import MODELE_REDACTION, ClientLLM, Compteur, appel_json
from projet.prompts import REDACTEUR_ITERATION, REDACTEUR_SYSTEME
from projet.referentiel import ChampAttendu
from projet.regles_arith import eclater_ihc
from projet.schemas import Element, SourceRef
from projet.textes import Localisation, extrait_court, localiser, localiser_exacte, phrases
from text_utils import normaliser

_TYPES = {"phrase", "titre", "liste", "trou"}
_STATUTS = {"dicte", "reformule", "normalise"}
_MARKDOWN = re.compile(r"(\*\*|__|^#+\s*|^\s*[-*]\s+(?=\S))", re.MULTILINE)


@dataclass(slots=True)
class ElementBrouillon:
    """Element redige avant verification : l'Element du contrat + ses citations localisees."""

    element: Element
    citations: list[str] = field(default_factory=list)
    localisations: list[Localisation] = field(default_factory=list)


@dataclass(slots=True)
class Brouillon:
    titre: str
    elements: list[ElementBrouillon]
    modele: str | None = None
    citations_introuvables: int = 0


def nettoyer_markdown(texte: str) -> str:
    """Retire les marqueurs markdown residuels (le contrat interdit le markdown)."""
    texte = _MARKDOWN.sub("", texte)
    return re.sub(r"[ \t]+", " ", texte).strip()


def sources_dictee(locs: list[Localisation]) -> list[SourceRef]:
    return [SourceRef(kind="dictee", ref="dictee", libelle="Dictée", extrait=extrait_court(l.extrait),
                      debut=l.debut, fin=l.fin) for l in locs]


def element_trou(id_: str, champ: ChampAttendu, section: str) -> Element:
    """Element 'trou' : libelle du champ, options kb, obligatoire."""
    src = champ.source_exigence
    sources = [src] if src else []
    return Element(
        id=id_, section_id=section, type="trou", texte=champ.libelle, statut="a_completer",
        confiance=round(champ.confiance_source, 2), niveau="moyenne", sources=sources,
        explication="Champ obligatoire non dicté pour ce contexte : à compléter par le pathologiste.",
        champ_id=champ.id, obligatoire=True, options=list(champ.options), unite=champ.unite,
    )


def _section_valide(section: str, ids_sections: list[str]) -> str:
    if section in ids_sections:
        return section
    repli = {"ihc": "microscopie", "renseignements": "renseignements", "clinique": "renseignements",
             "macro": "macroscopie", "micro": "microscopie", "cytologie": "microscopie"}
    cible = repli.get(section, "microscopie")
    if cible in ids_sections:
        return cible
    return "microscopie" if "microscopie" in ids_sections else ids_sections[-1]


def _localiser_marqueur(item: str, dictee: str) -> Localisation | None:
    """Empan dicte d'un item « marqueur : resultat » : du marqueur jusqu'a la fin de sa proposition."""
    marqueur = item.split(":", 1)[0].strip()
    loc = localiser_exacte(marqueur, dictee) if marqueur else None
    if loc is None:
        return None
    suite = dictee[loc.fin:]
    reste = re.search(r"[,;.\n]", suite)
    fin = loc.fin + (reste.start() if reste else len(suite))
    # Dictee sans ponctuation : on s'arrete au mot de resultat (« positif », « négatif », « exprimé »…)
    # ou, a defaut, apres 4 mots ; l'empan d'un marqueur ne deborde jamais sur le marqueur suivant.
    resultat = re.search(r"\b(?:positi\w*|n[ée]gati\w*|exprim\w*|focal\w*|diffus\w*|conserv\w*|perdu\w*)\b",
                         dictee[loc.fin:fin], re.IGNORECASE)
    liaison = re.search(r"\s(?:et|puis|ainsi que)\s", dictee[loc.fin:fin], re.IGNORECASE)
    if liaison and (not resultat or liaison.start() < resultat.start()):
        fin = loc.fin + liaison.start()  # « TTF1 et la cytokératine… » : TTF1 s'arrete a la liaison
    elif resultat:
        fin = loc.fin + resultat.end()
    else:
        mots = list(re.finditer(r"\S+", dictee[loc.fin:fin]))
        if len(mots) > 4:
            fin = loc.fin + mots[3].end()
    return Localisation(loc.debut, fin, dictee[loc.debut:fin], "exacte")


def _construire(donnees: dict[str, object], dictee: str, ids_sections: list[str],
                champs_trous: dict[str, ChampAttendu], ids_existants: dict[str, Element] | None,
                prochain_id: int) -> tuple[list[ElementBrouillon], int, int]:
    """Transforme la sortie LLM en elements du contrat (citations localisees)."""
    res: list[ElementBrouillon] = []
    introuvables = 0
    utilises: set[str] = set()
    for brut in donnees.get("elements") or []:
        if not isinstance(brut, dict):
            continue
        type_ = str(brut.get("type") or "phrase")
        if type_ not in _TYPES:
            type_ = "phrase"
        texte = nettoyer_markdown(str(brut.get("texte") or ""))
        if not texte:
            continue
        section = _section_valide(str(brut.get("section") or ""), ids_sections)
        id_existant = str(brut.get("id")) if brut.get("id") else None
        if ids_existants is not None and id_existant in ids_existants and id_existant not in utilises:
            id_ = id_existant
        else:
            id_ = f"e{prochain_id}"
            prochain_id += 1
        utilises.add(id_)
        if type_ == "trou":
            champ = champs_trous.get(str(brut.get("champ_id") or ""))
            if champ is None:
                continue  # trou non demande : jamais de trou invente
            res.append(ElementBrouillon(element_trou(id_, champ, section)))
            continue
        citations = [str(c) for c in (brut.get("citations") or []) if isinstance(c, str) and c.strip()][:4]
        locs = [l for l in (localiser(c, dictee, tolerante=True) for c in citations) if l is not None]
        if citations and not locs:
            introuvables += 1
        if not locs:
            # Repli : ancrage de l'element lui-meme dans la dictee.
            l = localiser(texte, dictee, tolerante=True)
            if l is not None:
                locs = [l]
        if section == "ihc" and type_ == "liste" and ":" in texte:
            # Un item d'IHC est ancre sur SON marqueur, jamais sur toute la fin de la dictee.
            loc_m = _localiser_marqueur(texte, dictee)
            if loc_m is not None and (not locs or sum(l.fin - l.debut for l in locs) > 2 * (loc_m.fin - loc_m.debut)):
                locs = [loc_m]
        statut = str(brut.get("statut") or "reformule")
        element = Element(
            id=id_, section_id=section, type=type_, texte=texte,
            statut=statut if statut in _STATUTS else "reformule",  # type: ignore[arg-type]
            confiance=0.5, niveau="basse", sources=sources_dictee(locs),
            champ_id=str(brut["champ_id"]) if brut.get("champ_id") else None,
        )
        items = eclater_ihc(texte) if (type_ == "liste" or (section == "ihc" and type_ == "phrase")) else []
        if len(items) >= 2:
            # Un element de liste PAR marqueur : « TTF1 : positif Cytokératine 7 : positif » ne reste jamais en un bloc.
            for k, item in enumerate(items):
                if k:
                    id_ = f"e{prochain_id}"
                    prochain_id += 1
                loc_item = _localiser_marqueur(item, dictee) or localiser(item, dictee, tolerante=True)
                locs_item = [loc_item] if loc_item is not None else locs
                res.append(ElementBrouillon(
                    element.model_copy(update={"id": id_, "texte": item, "type": "liste", "sources": sources_dictee(locs_item)}),
                    [item], locs_item))
            continue
        res.append(ElementBrouillon(element, citations, locs))
    return res, introuvables, prochain_id


def _bloc_trous(champs: list[ChampAttendu]) -> str:
    return json.dumps([{"champ_id": c.id, "libelle": c.libelle, "section": c.section} for c in champs],
                      ensure_ascii=False)


async def rediger(dictee: str, *, titre_hint: str, contexte_txt: str, sections: list[tuple[str, str]],
                  trous: list[ChampAttendu], exemples: list[dict[str, object]], client: ClientLLM,
                  compteur: Compteur, modele: str = MODELE_REDACTION, delai_s: float = 35.0,
                  existants: list[Element] | None = None, complement: str | None = None,
                  prochain_id: int = 1) -> Brouillon:
    """Agent complet (generation ou iteration si ``existants`` est fourni)."""
    ids_sections = [s for s, _ in sections]
    systeme = REDACTEUR_SYSTEME + (REDACTEUR_ITERATION if existants is not None else "")
    parties = [
        f"CONTEXTE : {contexte_txt}",
        "GABARIT (id : titre) : " + " ; ".join(f"{i} : {t}" for i, t in sections),
        "CHAMPS A COMPLETER : " + (_bloc_trous(trous) if trous else "aucun"),
    ]
    if exemples:
        textes = [str(e.get("texte") or "")[:900] for e in exemples if e.get("texte")]
        if textes:
            parties.append("EXEMPLES DE STYLE (forme seulement) :\n" + "\n---\n".join(textes))
    if titre_hint:
        parties.append(f"INDICATION DE TITRE : {titre_hint}")
    if existants is not None:
        parties.append("ELEMENTS EXISTANTS :\n" + json.dumps(
            [{"id": e.id, "section": e.section_id, "type": e.type, "texte": e.texte, "champ_id": e.champ_id}
             for e in existants], ensure_ascii=False))
        parties.append("DICTEE INITIALE :\n<<<\n" + dictee + "\n>>>")
        parties.append("DICTEE COMPLEMENTAIRE :\n<<<\n" + (complement or "") + "\n>>>")
    else:
        parties.append("DICTEE :\n<<<\n" + dictee + "\n>>>")
    donnees, reponse = await appel_json(client, compteur, etiquette="redacteur", modele=modele,
                                        systeme=systeme, utilisateur="\n\n".join(parties),
                                        max_tokens=4000, delai_s=delai_s)
    # Les citations sont cherchees dans la dictee COMPLETE (initiale + complement en iteration).
    ids_ex = {e.id: e for e in existants} if existants is not None else None
    elements, introuvables, _ = _construire(donnees, dictee, ids_sections,
                                            {c.id: c for c in trous}, ids_ex, prochain_id)
    titre = nettoyer_markdown(str(donnees.get("titre") or titre_hint or "EXAMEN ANATOMOPATHOLOGIQUE")).upper()
    return Brouillon(titre=titre, elements=elements, modele=reponse.model, citations_introuvables=introuvables)


_MARQUEURS_SECTION: list[tuple[str, str]] = [
    ("renseignement", "renseignements"), ("clinique", "renseignements"),
    ("macroscop", "macroscopie"), ("microscop", "microscopie"), ("histolog", "microscopie"),
    ("cytolog", "microscopie"), ("immuno", "ihc"), ("conclusion", "conclusion"),
]


def projet_minimal(dictee: str, sections: list[tuple[str, str]], prochain_id: int = 1) -> list[ElementBrouillon]:
    """Repli N3 : chaque phrase dictee, telle quelle, dans la section annoncee par le praticien.

    Aucune reformulation, aucun ajout : le projet est pauvre mais strictement fidele.
    """
    ids_sections = [s for s, _ in sections]
    section = "microscopie" if "microscopie" in ids_sections else ids_sections[0]
    res: list[ElementBrouillon] = []
    for debut, fin, texte in phrases(dictee):
        norm = normaliser(texte[:40])
        for mot, sec in _MARQUEURS_SECTION:
            if norm.startswith(mot) or norm.lstrip("- ").startswith(mot):
                section = _section_valide(sec, ids_sections)
                break
        loc = Localisation(debut, fin, texte, "exacte")
        el = Element(id=f"e{prochain_id}", section_id=section, type="phrase", texte=texte.strip(),
                     statut="dicte", confiance=0.9, niveau="haute", sources=sources_dictee([loc]),
                     explication="Phrase dictée reprise telle quelle (mode dégradé).")
        prochain_id += 1
        res.append(ElementBrouillon(el, [texte], [loc]))
    return res
