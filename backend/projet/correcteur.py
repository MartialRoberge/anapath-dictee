"""Agent correcteur phonetique : erreurs de transcription STT, avec journal explicable.

Trois passes, de la plus sure a la moins sure :
1. VARIANTES CONNUES (deterministe) : formes observees du lexique (« barretis »
   -> « Barety »), appliquees seulement si le contexte requis est present ;
2. PROXIMITE (deterministe) : un mot inconnu phonetiquement identique et a
   faible distance d'edition d'un terme du vocabulaire ACP (« lobullaire » ->
   « lobulaire ») ; les flexions (acineux/acineuse) ne sont jamais corrigees ;
3. ARBITRAGE (Mistral rapide) : uniquement pour les cas ambigus (plusieurs
   candidats ou distance 2).

Une correction sous le seuil de confiance n'est PAS appliquee : elle est
signalee (alerte 'phonetique') pour que le praticien tranche. Les offsets sont
exacts dans ``dictee.brute`` ; ``appliquer_corrections`` produit la dictee
corrigee.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

from projet.llm_client import MODELE_RAPIDE, ClientLLM, Compteur, appel_json
from projet.referentiel import EntreeLexique
from projet.schemas import Correction, SourceRef
from projet.textes import jetons
from text_utils import normaliser

#: Au-dessus : correction appliquee. En dessous : proposee et signalee seulement.
SEUIL_APPLICATION: float = 0.75

_SUFFIXES_FLEXION: tuple[str, ...] = (
    "ienne", "euse", "elle", "ive", "eux", "ien", "ale", "aux", "ees", "ee", "es",
    "al", "el", "if", "s", "x", "e",
)


def cle_phonetique(mot: str) -> str:
    """Cle phonetique francaise simplifiee (type Soundex FR / Phonex).

    Deux graphies qui se prononcent pareil (« glison »/« gleason » non, mais
    « lobullaire »/« lobulaire », « filode »/« phyllode ») partagent la cle.
    """
    s = re.sub(r"[^a-z]", "", normaliser(mot))
    s = re.sub(r"(.)\1+", r"\1", s)  # lettres doublees d'abord (« omme » = « ome »)
    regles: list[tuple[str, str]] = [
        (r"ph", "f"), (r"th", "t"), (r"sch", "S"), (r"ch", "S"), (r"gu(?=[eiy])", "g"),
        (r"qu", "k"), (r"ck", "k"), (r"q", "k"), (r"c(?=[eiy])", "s"), (r"c", "k"),
        (r"g(?=[eiy])", "j"), (r"x", "ks"), (r"w", "v"), (r"y", "i"), (r"z", "s"), (r"h", ""),
        (r"eau", "o"), (r"au", "o"), (r"ai", "e"), (r"ei", "e"), (r"ou", "u"),
        (r"(?:an|am|en|em)(?=[^aeiou]|$)", "A"), (r"(?:on|om)(?=[^aeiou]|$)", "O"),
        (r"(?:ain|ein|in|im|un)(?=[^aeiou]|$)", "I"),
        (r"(?:er|ez|et)$", "e"),
    ]
    for motif, remplacement in regles:
        s = re.sub(motif, remplacement, s)
    s = re.sub(r"e$", "", s)
    s = re.sub(r"[stdxp]$", "", s)
    s = re.sub(r"(.)\1+", r"\1", s)  # lettres doublees
    return s


def distance_edition(a: str, b: str) -> int:
    """Distance de Levenshtein (insertion, suppression, substitution)."""
    if a == b:
        return 0
    prec = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cour = [i]
        for j, cb in enumerate(b, 1):
            cour.append(min(prec[j] + 1, cour[j - 1] + 1, prec[j - 1] + (ca != cb)))
        prec = cour
    return prec[-1]


def _radical(mot: str) -> str:
    for suf in _SUFFIXES_FLEXION:
        if mot.endswith(suf) and len(mot) - len(suf) >= 4:
            return mot[: -len(suf)]
    return mot


def est_flexion(a: str, b: str) -> bool:
    """« acineux »/« acineuse », « tumeur »/« tumeurs » : meme mot flechi, pas une erreur STT."""
    return _radical(a) == _radical(b) or a.rstrip("sx") == b.rstrip("sx")


@dataclass(slots=True)
class _Cas:
    """Correction candidate avant decision."""

    debut: int
    fin: int
    original: str
    candidats: list[str]
    confiance: float
    raison: str
    sources: list[SourceRef] = field(default_factory=list)
    ambigu: bool = False
    contexte_ok: bool = True


@dataclass(slots=True)
class ResultatCorrection:
    corrections: list[Correction]
    corrigee: str
    appel_llm: bool = False
    details: list[str] = field(default_factory=list)


def _source_agent(texte: str) -> SourceRef:
    return SourceRef(kind="agent", ref="correcteur", libelle="Correcteur phonétique", extrait=texte)


def _contexte_present(norm_dictee: str, contexte_requis: list[str]) -> bool:
    if not contexte_requis:
        return True
    return any(normaliser(c) in norm_dictee for c in contexte_requis)


def _meme_forme(a: str, b: str) -> bool:
    return a == b or (len(a) > 3 and len(b) > 3 and a.rstrip("sx") == b.rstrip("sx"))


def _chevauche(debut: int, fin: int, pris: list[tuple[int, int]]) -> bool:
    return any(debut < f and fin > d for d, f in pris)


def detecter_variantes(brute: str, lexique: list[EntreeLexique]) -> list[_Cas]:
    """Passe 1 : formes connues du lexique, contexte requis verifie.

    Le contexte est cherche dans la dictee ET dans les termes deja reconnus
    (« glison » se corrige si « adenocarcynome » a ete reconnu « adenocarcinome »).
    """
    norm = normaliser(brute)
    toks = jetons(brute)
    par_premier: dict[str, list[int]] = {}
    for i, j in enumerate(toks):
        par_premier.setdefault(j.forme.rstrip("sx") if len(j.forme) > 3 else j.forme, []).append(i)
    trouves: list[tuple[EntreeLexique, str, float, int, int]] = []
    pris: list[tuple[int, int]] = []
    # Les variantes longues d'abord : « tu meurs » avant « meurs ».
    paires = sorted(
        ((e, forme, conf) for e in lexique for forme, conf in e.variantes),
        key=lambda p: -len(p[1]),
    )
    for entree, forme, conf in paires:
        cibles = [j.forme for j in jetons(forme)]
        terme = [j.forme for j in jetons(entree.terme)]
        if not cibles or cibles == terme:
            continue  # accent, casse ou trait d'union seulement : pas une erreur STT
        if len(cibles) == 1 and len(terme) == 1 and est_flexion(cibles[0], terme[0]):
            continue  # pluriel / feminin du terme : jamais corrige
        cle0 = cibles[0].rstrip("sx") if len(cibles[0]) > 3 else cibles[0]
        for i in par_premier.get(cle0, []):
            if i + len(cibles) > len(toks):
                continue
            if not all(_meme_forme(toks[i + k].forme, cibles[k]) for k in range(len(cibles))):
                continue
            debut, fin = toks[i].debut, toks[i + len(cibles) - 1].fin
            if _chevauche(debut, fin, pris):
                continue
            trouves.append((entree, forme, conf, debut, fin))
            pris.append((debut, fin))
    contexte = norm + " " + " ".join(normaliser(e.terme) for e, *_ in trouves if not e.contexte_requis)
    cas: list[_Cas] = []
    for entree, forme, conf, debut, fin in trouves:
        ok = _contexte_present(contexte, entree.contexte_requis)
        confiance = conf if ok else min(conf, 0.45)
        raison = f"variante phonetique connue de « {entree.terme} »"
        if entree.contexte_requis:
            raison += (" ; contexte présent (" + ", ".join(entree.contexte_requis[:3]) + ")") if ok \
                else " ; contexte requis absent, correction non appliquée"
        cas.append(_Cas(debut, fin, brute[debut:fin], [entree.terme], confiance,
                        raison, [entree.source, _source_agent(forme)], contexte_ok=ok))
    return cas


def detecter_proximites(brute: str, vocabulaire: list[str], deja: list[_Cas]) -> list[_Cas]:
    """Passe 2 : mot inconnu proche (cle phonetique + distance) d'un terme du vocabulaire."""
    connus: dict[str, str] = {}
    for terme in vocabulaire:
        t = normaliser(terme)
        if " " not in t and len(t) >= 5:
            connus.setdefault(t, terme)
    cles: dict[str, list[str]] = {}
    for t in connus:
        cles.setdefault(cle_phonetique(t), []).append(t)
    pris = [(c.debut, c.fin) for c in deja]
    cas: list[_Cas] = []
    for j in jetons(brute):
        f = j.forme
        if len(f) < 6 or not f.isalpha() or f in connus or _chevauche(j.debut, j.fin, pris):
            continue
        cle = cle_phonetique(f)
        candidats: list[tuple[int, str]] = []
        for t in cles.get(cle, []):
            d = distance_edition(f, t)
            if d <= 2 and not est_flexion(f, t):
                candidats.append((d, t))
        # Distance 1 sur un mot long, meme si la cle differe (mycosecretion).
        if not candidats and len(f) >= 9:
            for t in connus:
                if abs(len(t) - len(f)) <= 1 and distance_edition(f, t) == 1 and not est_flexion(f, t):
                    candidats.append((1, t))
        if not candidats:
            continue
        candidats.sort()
        termes = [connus[t] for _, t in candidats]
        unique = len(candidats) == 1
        dmin = candidats[0][0]
        confiance = 0.8 if (unique and dmin == 1) else (0.7 if unique else 0.6)
        raison = (f"graphie proche de « {termes[0]} » (même prononciation, distance {dmin})"
                  if cle_phonetique(candidats[0][1]) == cle else
                  f"une lettre d'écart avec « {termes[0]} »")
        cas.append(_Cas(j.debut, j.fin, brute[j.debut:j.fin], termes[:4], confiance, raison,
                        [_source_agent(brute[j.debut:j.fin])], ambigu=confiance < SEUIL_APPLICATION))
    return cas


_PROMPT_ARBITRAGE = """Tu es le correcteur phonetique de MARC (aide a la redaction de comptes rendus d'anatomie et cytologie pathologiques).
Une dictee vocale a ete transcrite automatiquement. Pour chaque cas, choisis le terme que le pathologiste a
VRAISEMBLABLEMENT prononce parmi les candidats, d'apres le contexte. Si aucun candidat n'est plus probable que le
mot transcrit, reponds null. Ne propose JAMAIS un terme hors de la liste des candidats.
Reponds en JSON strict : {"decisions": [{"id": "c1", "choix": "terme ou null", "confiance": 0.0-1.0, "raison": "courte"}]}"""


async def arbitrer(cas: list[_Cas], brute: str, client: ClientLLM, compteur: Compteur,
                   modele: str = MODELE_RAPIDE, delai_s: float = 8.0) -> bool:
    """Passe 3 : arbitrage LLM des seuls cas ambigus (contexte present). Modifie ``cas`` en place."""
    ambigus = [c for c in cas if c.ambigu and c.contexte_ok]
    if not ambigus:
        return False
    items = []
    for i, c in enumerate(ambigus):
        g, d = max(0, c.debut - 80), min(len(brute), c.fin + 80)
        items.append({"id": f"c{i}", "mot_transcrit": c.original, "candidats": c.candidats,
                      "contexte": brute[g:d]})
    donnees, _ = await appel_json(client, compteur, etiquette="correcteur", modele=modele,
                                  systeme=_PROMPT_ARBITRAGE,
                                  utilisateur=json.dumps({"cas": items}, ensure_ascii=False),
                                  max_tokens=600, delai_s=delai_s)
    decisions = {str(d.get("id")): d for d in donnees.get("decisions", []) if isinstance(d, dict)}
    for i, c in enumerate(ambigus):
        d = decisions.get(f"c{i}")
        if not d:
            continue
        choix = d.get("choix")
        try:
            conf_llm = float(d.get("confiance") or 0)
        except (TypeError, ValueError):
            conf_llm = 0.0
        if isinstance(choix, str) and choix in c.candidats:
            c.candidats.remove(choix)
            c.candidats.insert(0, choix)
            c.confiance = round(min(0.85, max(c.confiance, conf_llm)), 2) if conf_llm >= SEUIL_APPLICATION \
                else min(c.confiance, conf_llm or c.confiance)
            c.raison += f" ; arbitré par le modèle : « {choix} »"
            if d.get("raison"):
                c.raison += f" ({str(d['raison'])[:80]})"
        else:
            c.confiance = min(c.confiance, 0.5)
            c.raison += " ; le modèle ne tranche pas"
        c.sources.append(SourceRef(kind="agent", ref=f"correcteur:{modele}", libelle=f"Arbitrage {modele}"))
    return True


def appliquer_corrections(brute: str, corrections: list[Correction]) -> str:
    """Construit la dictee corrigee en appliquant les corrections retenues (offsets brute)."""
    morceaux: list[str] = []
    curseur = 0
    for c in sorted((c for c in corrections if c.appliquee), key=lambda c: c.debut):
        if c.debut < curseur:
            continue  # chevauchement impossible en pratique, ignore par securite
        morceaux.append(brute[curseur:c.debut])
        morceaux.append(c.corrige)
        curseur = c.fin
    morceaux.append(brute[curseur:])
    return "".join(morceaux)


def position_corrigee(brute_pos: int, corrections: list[Correction]) -> int:
    """Convertit un offset de la dictee brute en offset de la dictee corrigee."""
    decalage = 0
    for c in sorted((c for c in corrections if c.appliquee), key=lambda c: c.debut):
        if c.fin <= brute_pos:
            decalage += len(c.corrige) - (c.fin - c.debut)
    return brute_pos + decalage


async def corriger(brute: str, lexique: list[EntreeLexique], vocabulaire: list[str],
                   client: ClientLLM | None, compteur: Compteur, *, id_prefixe: str = "corr",
                   decalage: int = 0, utiliser_llm: bool = True) -> ResultatCorrection:
    """Agent complet. ``decalage`` : offset a ajouter (iteration : dictee complementaire)."""
    cas = detecter_variantes(brute, lexique)
    cas += detecter_proximites(brute, vocabulaire, cas)
    appel = False
    details: list[str] = []
    if utiliser_llm and client is not None and any(c.ambigu and c.contexte_ok for c in cas):
        try:
            appel = await arbitrer(cas, brute, client, compteur)
        except Exception as exc:  # noqa: BLE001 - l'arbitrage est facultatif
            details.append(f"Arbitrage indisponible ({type(exc).__name__}) : cas ambigus non appliques")
    corrections: list[Correction] = []
    for i, c in enumerate(sorted(cas, key=lambda c: c.debut)):
        appliquee = c.confiance >= SEUIL_APPLICATION and c.contexte_ok
        corrige = c.candidats[0]
        if c.original[:1].isupper() and corrige[:1].islower():
            corrige = corrige[:1].upper() + corrige[1:]  # majuscule de debut de phrase conservee
        corrections.append(Correction(
            id=f"{id_prefixe}{i + 1}", original=c.original, corrige=corrige,
            debut=c.debut + decalage, fin=c.fin + decalage, confiance=round(c.confiance, 2),
            raison=c.raison, candidats=c.candidats, sources=c.sources, appliquee=appliquee,
        ))
    locales = [c.model_copy(update={"debut": c.debut - decalage, "fin": c.fin - decalage}) for c in corrections]
    corrigee = appliquer_corrections(brute, locales)
    for c in corrections:
        etat = "appliquée" if c.appliquee else "proposée, non appliquée"
        details.append(f"« {c.original} » -> « {c.corrige} » ({c.confiance:.2f}, {etat})")
    return ResultatCorrection(corrections, corrigee, appel, details)
