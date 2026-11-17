"""Acces a la base de connaissances structuree `backend/kb/` (kb_marc_v3).

INTERFACE STABLE : le pipeline n'utilise que les methodes de `KB` ci-dessous.
Les signatures du contrat ne changent pas ; des methodes ADDITIVES sont ajoutees
(candidats_phonetiques, adicap_*, snomed_*, evaluer_regle, ...). Les donnees sont
produites par `scripts/build_kb.py` (jamais editees a la main, hors `kb/seeds/`).

Regles de conception (audit PO-1, section 8) :
- chargement PARESSEUX (un fichier JSON n'est lu qu'au premier besoin) et cache ;
- REPLI GRACIEUX : aucun accesseur ne leve d'exception ; un fichier absent,
  corrompu ou une cle inconnue donne une valeur vide (liste vide, None, {}),
  jamais une valeur inventee ;
- aucune donnee medicale ni patient n'est lue ni ecrite ici (base documentaire).

Ce module contient aussi la normalisation de texte et la CLE PHONETIQUE FRANCAISE
(algorithme « Phonex-FR », voisin de Soundex/Phonex), partagees par le build
(cle de chaque terme et variante du lexique) et par le correcteur STT.
"""
from __future__ import annotations

import json
import os
import re
import unicodedata
from pathlib import Path
from typing import Any

# Dossier des donnees generees (surchargeable pour les tests de build).
_KB_DIR_DEFAUT: Path = Path(__file__).resolve().parent.parent / "kb"


def kb_dir() -> Path:
    """Dossier de la base ; `MARC_KB_DIR` permet de pointer un build de test."""
    env = os.environ.get("MARC_KB_DIR")
    return Path(env) if env else _KB_DIR_DEFAUT


# ===========================================================================
# 1. Normalisation de texte (avec table d'offsets)
# ===========================================================================

_LIGATURES: dict[str, str] = {"œ": "oe", "Œ": "oe", "æ": "ae", "Æ": "ae"}
_APOSTROPHES = str.maketrans({"’": "'", "‘": "'", "`": "'", "´": "'"})


def _normaliser_car(c: str) -> str:
    """Un caractere -> sa forme normalisee (minuscule, sans accent), 0..2 caracteres."""
    if c in _LIGATURES:
        return _LIGATURES[c]
    c = c.translate(_APOSTROPHES)
    d = unicodedata.normalize("NFD", c)
    base = "".join(ch for ch in d if not unicodedata.combining(ch))
    return base.lower()


def normaliser(texte: str) -> str:
    """Minuscules, sans accents, ligatures developpees, apostrophes unifiees."""
    return "".join(_normaliser_car(c) for c in (texte or ""))


def normaliser_avec_index(texte: str) -> tuple[str, list[int]]:
    """Comme `normaliser`, avec `idx[i]` = position dans `texte` du caractere normalise i.

    `idx` a une case de plus (sentinelle = len(texte)) pour convertir une fin.
    Permet de retrouver les offsets dans la dictee d'origine apres normalisation.
    """
    out: list[str] = []
    idx: list[int] = []
    for i, c in enumerate(texte or ""):
        n = _normaliser_car(c)
        for ch in n:
            out.append(ch)
            idx.append(i)
    idx.append(len(texte or ""))
    return "".join(out), idx


# ===========================================================================
# 2. Cle phonetique francaise « Phonex-FR »
# ===========================================================================
# Principe : on ramene un mot a une chaine de phonemes grossiers (majuscules) qui
# neutralise les confusions typiques de la reconnaissance vocale en francais
# (e/é/è, c/k/qu, s/ss/z, ph/f, doubles consonnes, lettres finales muettes,
# voyelles nasales). Les espaces et traits d'union sont supprimes : « adeno
# carcinome » et « adénocarcinome » ont la MEME cle (erreur de segmentation STT).

_VOYELLES = "aeiouy"

# (motif, remplacement) appliques dans l'ordre sur un mot en minuscules ASCII.
# Les remplacements sont en MAJUSCULES pour ne plus etre reecrits ensuite.
_REGLES_PHON: list[tuple[re.Pattern[str], str]] = [
    (re.compile(p), r) for p, r in [
        (r"oe", "e"),                         # œ -> e (œsophage = ésophage)
        (r"^h", ""),                          # h initial muet
        (r"ph", "F"),
        (r"sch", "S"),
        (r"ch(?=[orly])", "K"),               # chondro, cholangio, chromo, chyle
        (r"ch", "S"),                         # chirurgie, chimie
        (r"gn", "N"),
        (r"(?:qu|cq|ck|q)", "K"),
        (r"gu(?=[eiy])", "G"),
        (r"g(?=[eiy])", "J"),
        (r"c(?=[eiy])", "S"),
        (r"ti(?=on|al|el|eu)", "SI"),
        (r"x$", ""),                          # x final muet (bronchiaux)
        (r"x", "KS"),
        (r"w", "V"),
        (r"z", "S"),
        (r"c", "K"),
        (r"k", "K"),
        (r"h", ""),
        (r"eau|au", "O"),
        (r"eu", "E"),
        (r"ou", "U"),
        (r"oi|oy", "OA"),
        (r"ai|ei|ay|ey", "E"),
        (r"(?:ain|ein|aim|eim)(?![aeiouyn])", "IN"),
        (r"ien(?![aeiouyn])", "IIN"),
        (r"(?:in|im|yn|ym|un|um)(?![aeiouynm])", "IN"),
        (r"(?:an|am|en|em)(?![aeiouynm])", "AN"),
        (r"(?:on|om)(?![aeiouynm])", "ON"),
        (r"y", "I"),
        (r"[aeiou]", lambda m: m.group(0).upper()),  # type: ignore[arg-type]
    ]
]


def _phon_mot(mot: str) -> str:
    """Cle d'un mot ASCII minuscule (lettres seules ou chiffres seuls)."""
    if mot.isdigit():
        return mot
    s = mot
    for motif, rempl in _REGLES_PHON:
        s = motif.sub(rempl, s)
    s = s.upper()
    # consonnes/voyelles doublees -> simples (pas sur les sigles courts : TTF, CDX)
    if len(mot) > 4:
        s = re.sub(r"(.)\1+", r"\1", s)
    # lettres finales muettes (pluriel, e muet, t/d final) sur mots assez longs
    if len(s) > 3:
        s = re.sub(r"[STDX]$", "", s)
    if len(s) > 3:
        s = re.sub(r"E$", "", s)
    return s


def cle_phonetique(texte: str) -> str:
    """Cle phonetique d'un terme ou d'une expression (insensible aux espaces/traits d'union).

    Exemples : « Barety », « barretis » et « baretti » donnent la meme cle ;
    « adénocarcinome » = « adeno carcinome ».
    """
    norm = normaliser(texte).replace("'", " ")
    jetons = re.findall(r"[a-z]+|\d+", norm)
    return "".join(_phon_mot(j) for j in jetons)


def distance_levenshtein(a: str, b: str, max_dist: int | None = None) -> int:
    """Distance d'edition classique ; coupe tot si `max_dist` est depassee."""
    if a == b:
        return 0
    if len(a) < len(b):
        a, b = b, a
    if not b:
        return len(a)
    precedent = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        courant = [i]
        for j, cb in enumerate(b, 1):
            courant.append(min(precedent[j] + 1, courant[j - 1] + 1,
                               precedent[j - 1] + (ca != cb)))
        if max_dist is not None and min(courant) > max_dist:
            return max_dist + 1
        precedent = courant
    return precedent[-1]


def similarite_phonetique(a: str, b: str) -> float:
    """Similarite 0..1 entre deux termes, par distance d'edition sur les cles."""
    ka, kb = cle_phonetique(a), cle_phonetique(b)
    if not ka or not kb:
        return 0.0
    if ka == kb:
        return 1.0
    d = distance_levenshtein(ka, kb)
    return max(0.0, 1.0 - d / max(len(ka), len(kb)))


# ===========================================================================
# 3. Mini-DSL de regles de coherence (evaluation sure, sans exec)
# ===========================================================================
# Une expression est soit une constante, soit {"var": nom}, soit {"op": ..., "args": [...]}.
# Operateurs : > < >= <= == != and or not present absent in sum max min abs mul sub
# Une variable absente fait echouer toute comparaison (la regle ne se declenche pas) :
# on ne declare jamais une incoherence sur une valeur qu'on ne connait pas.

_ABSENT = object()


def _val(expr: Any, valeurs: dict[str, Any]) -> Any:
    if isinstance(expr, dict):
        if "var" in expr:
            v = valeurs.get(expr["var"], _ABSENT)
            return _ABSENT if v is None else v
        op = expr.get("op")
        args = expr.get("args", [])
        if op in ("present", "absent"):
            v = _val(args[0], valeurs) if args else _ABSENT
            ok = v is not _ABSENT and v != "" and v != []
            return ok if op == "present" else not ok
        if op in ("and", "or"):
            res = [bool(_val(a, valeurs)) if _val(a, valeurs) is not _ABSENT else False
                   for a in args]
            return all(res) if op == "and" else any(res)
        if op == "not":
            v = _val(args[0], valeurs)
            return False if v is _ABSENT else (not bool(v))
        vals = [_val(a, valeurs) for a in args]
        if op == "in":
            if vals[0] is _ABSENT or vals[1] is _ABSENT:
                return False
            return vals[0] in vals[1]
        if op in ("sum", "max", "min"):
            seq = vals[0] if len(vals) == 1 and isinstance(vals[0], list) else vals
            nums = [x for x in seq if isinstance(x, (int, float)) and not isinstance(x, bool)]
            if not nums or len(nums) != len(seq):
                return _ABSENT
            return {"sum": sum, "max": max, "min": min}[op](nums)
        if any(v is _ABSENT for v in vals):
            return _ABSENT if op in ("abs", "mul", "sub") else False
        try:
            if op == ">":
                return vals[0] > vals[1]
            if op == "<":
                return vals[0] < vals[1]
            if op == ">=":
                return vals[0] >= vals[1]
            if op == "<=":
                return vals[0] <= vals[1]
            if op == "==":
                return vals[0] == vals[1]
            if op == "!=":
                return vals[0] != vals[1]
            if op == "abs":
                return abs(vals[0])
            if op == "mul":
                return vals[0] * vals[1]
            if op == "sub":
                return vals[0] - vals[1]
        except TypeError:
            return _ABSENT if op in ("abs", "mul", "sub") else False
        return False
    return expr


def evaluer_condition(condition: Any, valeurs: dict[str, Any]) -> bool:
    """Evalue une condition DSL ; renvoie False en cas de doute ou d'erreur."""
    try:
        v = _val(condition, valeurs)
        return False if v is _ABSENT else bool(v)
    except Exception:
        return False


# ===========================================================================
# 4. Acces a la base
# ===========================================================================

_CONTEXTES: dict[str, str] = {
    "benin": "benin", "benigne": "benin", "non_tumoral": "benin", "non tumoral": "benin",
    "precancereux": "precancereux", "pre_cancereux": "precancereux",
    "in_situ": "precancereux", "insitu": "precancereux",
    "malin": "malin", "infiltrant": "malin", "tumoral": "malin", "invasif": "malin",
    "indetermine": "indetermine", "": "indetermine",
}
_PRELEVEMENTS: dict[str, str] = {
    "biopsie": "biopsie", "biopsies": "biopsie",
    "piece": "piece_operatoire", "piece_operatoire": "piece_operatoire",
    "piece operatoire": "piece_operatoire", "exerese": "piece_operatoire",
    "cytologie": "cytologie", "curage": "curage", "ganglion": "curage",
    "indetermine": "indetermine",
}


def _cle(valeur: str | None) -> str:
    return normaliser(valeur or "").strip().replace("-", "_")


def _contexte(valeur: str | None) -> str:
    return _CONTEXTES.get(_cle(valeur), _CONTEXTES.get(_cle(valeur).replace("_", " "), "indetermine"))


def _prelevement(valeur: str | None) -> str:
    c = _cle(valeur).replace("prelevement:", "")
    return _PRELEVEMENTS.get(c, _PRELEVEMENTS.get(c.replace("_", " "), "indetermine"))


def _organe_id(valeur: str | None) -> str:
    """'organe:poumon' | 'poumon' -> 'organe:poumon'."""
    v = (valeur or "").strip()
    if not v:
        return ""
    return v if v.startswith("organe:") else f"organe:{v}"


class KB:
    """Facade lecture seule sur la base de connaissances.

    `KB()` sans argument est une base VIDE (repli de niveau N0, utile aux tests du
    pipeline) ; `KB(dossier)` lit un build precis ; `get_kb()` lit la base du depot.
    """

    def __init__(self, repertoire: Path | None = None) -> None:
        self._dir: Path | None = repertoire
        self._cache: dict[str, Any] = {}

    # -- chargement -----------------------------------------------------
    def _charger(self, nom: str, defaut: Any) -> Any:
        """Lit `<nom>.json` une fois ; repli sur `defaut` si absent ou illisible."""
        if nom in self._cache:
            return self._cache[nom]
        try:
            if self._dir is None:
                raise FileNotFoundError(nom)
            with (self._dir / f"{nom}.json").open(encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            data = defaut
        self._cache[nom] = data
        return data

    def _liste(self, nom: str, cle: str | None = None) -> list[dict[str, Any]]:
        data = self._charger(nom, [])
        if cle is not None and isinstance(data, dict):
            data = data.get(cle, [])
        return data if isinstance(data, list) else []

    def disponible(self) -> bool:
        """True si la base est presente (manifeste lisible)."""
        return bool(self.manifeste())

    # -- contrat stable -------------------------------------------------
    def manifeste(self) -> dict[str, Any]:
        """{version, date_build, sources: [...], comptes: {collection: n}}"""
        m = self._charger("manifest", {})
        if not isinstance(m, dict) or not m:
            return {}
        return {**m, "sources": self._liste("sources")}

    def source(self, source_id: str) -> dict[str, Any] | None:
        """Entree du registre des sources : {id, titre, editeur, version, url, licence, fiabilite}."""
        sid = (source_id or "").strip()
        if sid and not sid.startswith("src:"):
            sid = f"src:{sid}"
        for s in self._liste("sources"):
            if s.get("id") == sid:
                return s
        return None

    def citations_source(self, source_id: str, limite: int = 50) -> dict[str, Any]:
        """Entrees de la base qui citent la source : {total, par_type{}, elements[{type, id, libelle, localisation}]}."""
        sid = (source_id or "").strip()
        if "_idx_citations" not in self._cache:
            idx: dict[str, list[tuple[str, dict[str, Any], str]]] = {}
            collections = (("champs", None, "champ"), ("regles", None, "regle"), ("plages", None, "plage"),
                           ("echelles", None, "echelle"), ("organes", None, "organe"),
                           ("prelevements", None, "prelevement"), ("gabarits", None, "gabarit"),
                           ("stations", None, "station"), ("snomed", "concepts", "snomed"),
                           ("lexique", None, "terme_lexique"), ("adicap_mappings", None, "mapping_adicap"),
                           ("exemples_style", None, "exemple_style"))
            for nom, cle, type_ in collections:
                for e in self._liste(nom, cle):
                    provs = [e.get("prov")] + list(e.get("prov_complementaires") or [])
                    for p in provs:
                        if isinstance(p, dict) and p.get("source_id"):
                            idx.setdefault(str(p["source_id"]), []).append((type_, e, str(p.get("localisation") or "")))
            self._cache["_idx_citations"] = idx
        entrees = self._cache["_idx_citations"].get(sid, [])
        par_type: dict[str, int] = {}
        for type_, _, _ in entrees:
            par_type[type_] = par_type.get(type_, 0) + 1
        # champs, regles, plages et echelles d'abord : ce sont les exigences que le praticien interroge.
        ordre = {"champ": 0, "regle": 1, "plage": 2, "echelle": 3}
        triees = sorted(entrees, key=lambda x: ordre.get(x[0], 9))
        elements = [{"type": t, "id": str(e.get("id") or ""),
                     "libelle": str(e.get("libelle") or e.get("terme") or e.get("nom") or e.get("id") or ""),
                     "localisation": loc} for t, e, loc in triees[: max(0, limite)]]
        return {"total": len(entrees), "par_type": par_type, "elements": elements}

    def organes(self) -> list[dict[str, Any]]:
        """[{id, libelle, synonymes[], adicap_d3[], categorie, prov}]"""
        return self._liste("organes")

    def organe(self, organe_id: str) -> dict[str, Any] | None:
        oid = _organe_id(organe_id)
        for o in self.organes():
            if o.get("id") == oid:
                return o
        return None

    # detection d'organes ------------------------------------------------
    def _motifs_organes(self) -> list[dict[str, Any]]:
        """Precompile, par organe, les regex a limites de mots (fortes et faibles)."""
        if "_motifs" in self._cache:
            return self._cache["_motifs"]
        compiles: list[dict[str, Any]] = []
        for o in self.organes():
            def comp(mots: list[str]) -> list[tuple[str, re.Pattern[str]]]:
                res = []
                for m in mots:
                    n = normaliser(m).strip()
                    if not n:
                        continue
                    # pluriel francais tolere (-s/-x), limites de mots strictes
                    res.append((n, re.compile(rf"(?<![a-z0-9]){re.escape(n)}(?:s|x)?(?![a-z0-9])")))
                return res
            fortes = list(o.get("synonymes", [])) + [o.get("libelle", "")]
            fortes += o.get("mots_cles_forts", [])
            compiles.append({
                "o": o,
                "forts": comp(sorted(set(fortes), key=len, reverse=True)),
                "faibles": comp(o.get("mots_cles_faibles", [])),
            })
        self._cache["_motifs"] = compiles
        return compiles

    def _pieges(self) -> list[re.Pattern[str]]:
        """Expressions neutralisees avant detection (« au sein de » n'est pas le sein)."""
        if "_pieges" not in self._cache:
            data = self._charger("detection", {})
            motifs = data.get("expressions_neutralisees", []) if isinstance(data, dict) else []
            self._cache["_pieges"] = [re.compile(normaliser(m)) for m in motifs]
        return self._cache["_pieges"]

    def detecter_organes(self, texte: str) -> list[dict[str, Any]]:
        """Organes mentionnes dans le texte : [{id, libelle, debut, fin, confiance}]

        `debut`/`fin` : premiere mention specifique, offsets dans `texte` d'origine.
        Un organe n'est retenu que s'il matche au moins un mot-cle SPECIFIQUE : les
        mots faibles (ganglion, lobectomie, cervical, hile...) ne declenchent jamais
        seuls (logique durcie de reports/knowledge.py). Les expressions piegees
        (« au sein de ») sont masquees avant recherche.
        """
        try:
            if not texte or not texte.strip():
                return []
            norm, idx = normaliser_avec_index(texte)
            masque = list(norm)
            for pat in self._pieges():
                for m in pat.finditer(norm):
                    for i in range(m.start(), m.end()):
                        masque[i] = "\u0000"
            norm_m = "".join(masque)
            resultats: list[dict[str, Any]] = []
            for c in self._motifs_organes():
                forts = [(kw, m) for kw, pat in c["forts"] for m in pat.finditer(norm_m)]
                if not forts:
                    continue
                faibles = {kw for kw, pat in c["faibles"] if pat.search(norm_m)}
                distincts = {kw for kw, _ in forts}
                premier = min((m for _, m in forts), key=lambda m: m.start())
                conf = min(0.95, 0.6 + 0.1 * (len(distincts) - 1) + 0.05 * min(len(faibles), 2))
                if normaliser(c["o"].get("libelle", "")) in distincts:
                    conf = max(conf, 0.85)
                resultats.append({
                    "id": c["o"]["id"],
                    "libelle": c["o"].get("libelle", ""),
                    "debut": idx[premier.start()],
                    "fin": idx[premier.end()] if premier.end() < len(idx) else len(texte),
                    "confiance": round(conf, 2),
                })
            resultats.sort(key=lambda r: (-r["confiance"], r["debut"]))
            return resultats[:5]
        except Exception:
            return []

    # champs --------------------------------------------------------------
    def champs(self, organe_id: str, prelevement: str | None, contexte_lesionnel: str) -> list[dict[str, Any]]:
        """Champs attendus : [{id, libelle, obligatoire, type, unite, options[], condition, prov}]

        Filtre par organe x prelevement x contexte. Sur une lesion BENIGNE aucun
        champ tumoral n'est renvoye (regle metier) : seuls les champs generiques
        non tumoraux le sont. Organe inconnu -> champs generiques seulement.
        """
        try:
            oid = _organe_id(organe_id)
            prel = _prelevement(prelevement)
            ctx = _contexte(contexte_lesionnel)
            out: list[dict[str, Any]] = []
            for c in self._liste("champs"):
                if c.get("organe_id") not in (oid, "organe:generique"):
                    continue
                appl = c.get("applicabilite", {})
                if ctx not in appl.get(prel, []):
                    continue
                if ctx == "benin" and c.get("tumoral", True):
                    continue
                out.append(c)
            return out
        except Exception:
            return []

    def champ(self, champ_id: str) -> dict[str, Any] | None:
        for c in self._liste("champs"):
            if c.get("id") == champ_id:
                return c
        return None

    # lexique -------------------------------------------------------------
    def lexique(self) -> list[dict[str, Any]]:
        """[{terme, variantes[], cle_phonetique, contexte_requis[], prov}]"""
        return self._liste("lexique")

    def _index_lexique(self) -> tuple[dict[str, list[int]], dict[str, list[int]]]:
        if "_idx_lex" in self._cache:
            return self._cache["_idx_lex"]
        par_forme: dict[str, list[int]] = {}
        par_cle: dict[str, list[int]] = {}
        for i, e in enumerate(self.lexique()):
            formes = [e.get("terme", "")] + list(e.get("variantes", []))
            for f in formes:
                nf = normaliser(f).strip()
                if nf:
                    par_forme.setdefault(nf, []).append(i)
            for k in {e.get("cle_phonetique", "")} | {
                d.get("cle", "") for d in e.get("variantes_detail", [])
            }:
                if k:
                    par_cle.setdefault(k, []).append(i)
        self._cache["_idx_lex"] = (par_forme, par_cle)
        return par_forme, par_cle

    def candidats_phonetiques(self, forme: str, distance_max: int = 1,
                              limite: int = 5) -> list[dict[str, Any]]:
        """Termes du lexique phonetiquement proches de `forme` (ADDITIF au contrat).

        Ordre : forme connue exacte (variante) > meme cle phonetique > cle a
        distance <= `distance_max` (mots de 6+ cles seulement). Renvoie
        [{terme, entree_id, via, distance, score, contexte_requis}]. Aucune
        correction n'est decidee ici : le correcteur applique les seuils et le
        contexte requis.
        """
        try:
            nf = normaliser(forme).strip()
            if not nf:
                return []
            lex = self.lexique()
            par_forme, par_cle = self._index_lexique()
            cle = cle_phonetique(nf)
            vus: dict[int, dict[str, Any]] = {}

            def ajouter(i: int, via: str, dist: int, score: float) -> None:
                if i not in vus or score > vus[i]["score"]:
                    e = lex[i]
                    vus[i] = {"terme": e.get("terme"), "entree_id": e.get("id"), "via": via,
                              "distance": dist, "score": round(score, 3),
                              "contexte_requis": e.get("contexte_requis", [])}
            for i in par_forme.get(nf, []):
                ajouter(i, "forme_connue", 0, 1.0)
            for i in par_cle.get(cle, []):
                ajouter(i, "cle_identique", 0, 0.9)
            if distance_max > 0 and len(cle) >= 6:
                for k, ids in par_cle.items():
                    if abs(len(k) - len(cle)) > distance_max:
                        continue
                    d = distance_levenshtein(cle, k, distance_max)
                    if 0 < d <= distance_max:
                        for i in ids:
                            ajouter(i, "cle_proche", d, 0.75 - 0.1 * d)
            res = sorted(vus.values(), key=lambda r: (-r["score"], r["terme"] or ""))
            return res[:limite]
        except Exception:
            return []

    # mesures et regles -----------------------------------------------------
    def plage_mesure(self, organe_id: str | None, champ_id: str) -> dict[str, Any] | None:
        """{unite, min, max, prov} plage plausible pour detecter mm/cm.

        `champ_id` : id complet (`champ:sein.taille_tumorale`) ou concept
        (`taille_tumorale`). Recherche d'abord la plage specifique a l'organe,
        sinon la plage generique du concept ; None si inconnue.
        """
        try:
            c = (champ_id or "").strip()
            c = c.split(".", 1)[1] if c.startswith("champ:") and "." in c else c.replace("champ:", "")
            oid = _organe_id(organe_id) if organe_id else ""
            plages = self._liste("plages")
            for cible in ([oid] if oid else []) + [None]:
                for p in plages:
                    if p.get("champ") == c and p.get("organe_id") == cible and not p.get("prelevement"):
                        return p
            return None
        except Exception:
            return None

    def plage_mesure_prelevement(self, organe_id: str | None, champ_id: str, prelevement: str | None) -> dict[str, Any] | None:
        """Plage propre a (organe, prelevement), ex. fragment de biopsie bronchique ; None si la base n'en a pas."""
        try:
            c = (champ_id or "").strip().replace("champ:", "")
            oid = _organe_id(organe_id) if organe_id else ""
            prel = _prelevement(prelevement) if prelevement else ""
            if not (oid and prel):
                return None
            for p in self._liste("plages"):
                if p.get("champ") == c and p.get("organe_id") == oid and p.get("prelevement") == prel:
                    return p
            return None
        except Exception:
            return None

    def regles(self) -> list[dict[str, Any]]:
        """Regles de coherence declaratives [{id, libelle, type, prov}]"""
        return self._liste("regles")

    def regle(self, regle_id: str) -> dict[str, Any] | None:
        for r in self.regles():
            if r.get("id") == regle_id:
                return r
        return None

    def evaluer_regle(self, regle_id: str, valeurs: dict[str, Any]) -> bool:
        """True si la regle declarative (a condition DSL) se declenche sur `valeurs`."""
        r = self.regle(regle_id)
        if not r or "condition" not in r:
            return False
        return evaluer_condition(r["condition"], valeurs)

    def echelles(self) -> list[dict[str, Any]]:
        return self._liste("echelles")

    def stations(self) -> list[dict[str, Any]]:
        return self._liste("stations")

    # style et gabarits -------------------------------------------------------
    def exemples_style(self, organe_id: str, limite: int = 3) -> list[dict[str, Any]]:
        """Formulations canoniques du laboratoire, verrouillees par organe, SANS donnee patient.

        Jamais d'exemple d'un autre organe (verrouillage) ; ordre stable : exemples
        complets et sans trou d'abord.
        """
        try:
            oid = _organe_id(organe_id)
            if not oid or limite <= 0:
                return []
            ex = [e for e in self._liste("exemples_style") if e.get("organe_id") == oid]
            ex.sort(key=lambda e: (not e.get("qualite", {}).get("complet", False),
                                   e.get("qualite", {}).get("a_trous", False), e.get("id", "")))
            return ex[:limite]
        except Exception:
            return []

    def gabarit(self, organe_id: str, prelevement: str | None) -> dict[str, Any] | None:
        """{id, sections:[{id,titre,ordre}], prov} ; repli : gabarit generique de la classe."""
        try:
            oid = _organe_id(organe_id)
            prel = _prelevement(prelevement)
            gabs = self._liste("gabarits")
            for o, p in ((oid, prel), ("organe:generique", prel), ("organe:generique", "indetermine")):
                for g in gabs:
                    if g.get("organe_id") == o and g.get("prelevement") == p:
                        return g
            return None
        except Exception:
            return None

    def prelevements(self) -> list[dict[str, Any]]:
        return self._liste("prelevements")

    # codage ---------------------------------------------------------------------
    def _thesaurus(self) -> dict[str, dict[str, Any]]:
        if "_thes" in self._cache:
            return self._cache["_thes"]
        data = self._charger("adicap_thesaurus", {})
        index: dict[str, dict[str, Any]] = {}
        try:
            cols = data.get("colonnes", [])
            prov = data.get("prov_commune", {})
            for ligne in data.get("concepts", []):
                e = dict(zip(cols, ligne))
                e["prov"] = {**prov, "localisation": f"adicapV3, uri {e.get('uri', '')}"}
                index[e["uri"]] = e
        except Exception:
            index = {}
        self._cache["_thes"] = index
        return index

    def adicap_concept(self, dictionnaire: str, code: str) -> dict[str, Any] | None:
        """Concept du thesaurus (dictionnaire D1..D8, code) ; None si inconnu."""
        for e in self._thesaurus().values():
            if e.get("dictionnaire") == dictionnaire and e.get("code") == code:
                return e
        return None

    def adicap_obsolete(self, dictionnaire: str, code: str) -> bool:
        e = self.adicap_concept(dictionnaire, code)
        return bool(e and e.get("fin_validite"))

    def adicap_mappings(self, organe_id: str | None = None) -> list[dict[str, Any]]:
        """Mappings lesion -> code ADICAP (candidats, jamais definitifs)."""
        m = self._liste("adicap_mappings")
        if organe_id:
            oid = _organe_id(organe_id)
            return [x for x in m if x.get("organe_id") == oid]
        return m

    def snomed_concepts(self, organe_id: str | None = None) -> list[dict[str, Any]]:
        """Concepts SNOMED CT (tous `non_valide` tant qu'aucune release officielle n'est chargee)."""
        c = self._liste("snomed", "concepts")
        if organe_id:
            oid = _organe_id(organe_id)
            return [x for x in c if oid in x.get("organe_ids", [])]
        return c


_KB: "KB | None" = None


def get_kb() -> "KB":
    global _KB
    if _KB is None:
        _KB = KB(kb_dir())
    return _KB


def reinitialiser_kb() -> None:
    """Vide le singleton (tests, rechargement apres un nouveau build)."""
    global _KB
    _KB = None
