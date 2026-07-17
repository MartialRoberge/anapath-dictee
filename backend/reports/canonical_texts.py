"""Formulations de REFERENCE du praticien (bible Excel du pathologiste).

Pour une lesion reconnue dans la dictee, retrouve la facon dont LE PRATICIEN
redige habituellement cette lesion (texte canonique issu de sa propre bible).
Injecte ensuite dans le prompt comme reference de VOCABULAIRE et de STRUCTURE :
MARC redige "comme lui", sans affirmer ce qui n'a pas ete dicte.

SECURITE DU MATCHING : l'appariement est VERROUILLE PAR ORGANE. Sans organe
reconnu, ou si l'organe de la dictee ne correspond a aucun chapitre de la bible,
on n'injecte RIEN (mieux vaut aucune reference qu'une reference d'un autre organe :
un texte colique injecte sur une biopsie bronchique serait pire que rien).

Source : backend/data/textes_canoniques.json (voir scripts/ingest_textes_canoniques.py).
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from text_utils import normaliser

_DATA_PATH: Path = Path(__file__).resolve().parent.parent / "data" / "textes_canoniques.json"

#: Score minimal d'appariement : 2 = au moins UN mot-cle long et discriminant
#: (les generiques sont ignores). Le verrou par organe borne deja le risque, un
#: seuil plus haut ferait rater les lesions au libelle court ("Gastrite...").
_MIN_SCORE: int = 2
#: Longueur max d'un texte injecte (evite de noyer le prompt).
_MAX_TEXTE: int = 900

#: Mots-cles trop generiques pour discriminer une lesion : ils matchent tout
#: ("muqueuse inflammatoire", "lesion connue"...). Ignores au scoring.
_GENERIC_KW: frozenset[str] = frozenset({
    "lesion", "lesions", "connue", "connu", "muqueuse", "inflammatoire",
    "inflammation", "normale", "normal", "biopsie", "biopsies", "fragment",
    "fragments", "chronique", "aigue", "aigu", "benin", "benigne", "maligne",
    "malin", "diffuse", "diffus", "focal", "focale", "type", "aspect", "avec",
    "sans", "petite", "petit", "grande", "grand", "piece", "prelevement",
    "reactionnelle", "reactionnel", "simple", "commun", "commune",
})

#: Organe applicatif -> chapitres (cat, motif d'organe) de la bible du praticien.
#: Le motif est teste en sous-chaine normalisee sur la colonne "organe".
_ORGAN_TO_CATALOG: dict[str, tuple[tuple[str, str], ...]] = {
    "poumon": (("THO", "poumon"), ("CYTO", "lba"), ("CYTO", "aspi bron")),
    "bronche": (("THO", "poumon"), ("CYTO", "aspi bron")),
    "plevre": (("THO", "poumon"),),
    "colon_rectum": (("DIG", "colo-rectal"),),
    "rectum": (("DIG", "colo-rectal"),),
    "estomac": (("DIG", "estomac"),),
    "appendice": (("DIG", "appendice"),),
    "vesicule_biliaire": (("DIG", "vesicule"),),
    "foie": (("DIG", "foie"),),
    "duodenum": (("DIG", "duodenum"),),
    "oesophage": (("DIG", "sophage"),),
    "canal_anal": (("DIG", "anus"),),
    "anus": (("DIG", "anus"),),
    "thyroide": (("ENDOC", "thyroide"), ("CYTO", "thyroide")),
    "parathyroide": (("ENDOC", "parathyroide"),),
    "surrenale": (("ENDOC", "surrenale"),),
    "endometre": (("GYN", "endometre"), ("GYN", "uterus")),
    "col_uterin": (("GYN", "col"), ("Cyto FCU", "fcu")),
    "ovaire": (("GYN", "ovaire"),),
    "trompe": (("GYN", "trompe"),),
    "vulve": (("GYN", "vulve"),),
    "vagin": (("GYN", "vagin"),),
    "vessie": (("URO", "vessie"), ("CYTO", "urine")),
    "rein": (("URO", "rein"),),
    "prostate": (("URO", "prostate"),),
    "testicule": (("URO", "testicule"), ("URO", "epididyme")),
    "ganglion": (("HEMATO", "gg"), ("CYTO", "ganglion")),
    "lymphome": (("HEMATO", "gg"),),
    "moelle_osseuse": (("HEMATO", "bom"),),
    "rate": (("HEMATO", "rate"),),
    "placenta": (("FOETO-P", "placenta"),),
    "oeil": (("OPH", "il"),),
    "larynx": (("ORL", "larynx"),),
    "glande_salivaire": (("ORL", "glande salivaire"),),
    "amygdale": (("ORL", "amygdale"),),
    "pharynx": (("ORL", "bouche"), ("ORL", "naso-sinusien")),
    "orl_tete_cou": (("ORL", "bouche"), ("ORL", "naso-sinusien"), ("ORL", "cou")),
    "myocarde": (("CV", "myocarde"),),
    "coeur": (("CV", "myocarde"), ("CV", "valve")),
    "artere": (("CV", "aorte"), ("CV", "bat"), ("CV", "endartere")),
    "aorte": (("CV", "aorte"),),
}


@lru_cache(maxsize=1)
def _catalog() -> tuple[dict[str, object], ...]:
    """Charge le catalogue une fois (cache process)."""
    if not _DATA_PATH.exists():
        return ()
    with _DATA_PATH.open(encoding="utf-8") as fh:
        return tuple(json.load(fh))


def _allowed_chapters(organes: list[str]) -> tuple[tuple[str, str], ...]:
    """Chapitres de bible autorises pour les organes detectes."""
    out: list[tuple[str, str]] = []
    for organe in organes:
        out.extend(_ORGAN_TO_CATALOG.get(organe, ()))
    return tuple(out)


def _entry_in_chapters(entry: dict[str, object],
                       chapters: tuple[tuple[str, str], ...]) -> bool:
    cat = str(entry.get("cat", ""))
    organe = normaliser(str(entry.get("organe", "")))
    return any(cat == c and motif in organe for c, motif in chapters)


def _score(kw: list[str], source_norm: str) -> int:
    """Mots-cles DISCRIMINANTS de la lesion presents dans la dictee.

    Les mots generiques sont ignores ; un mot long (>=6) compte double.
    """
    total = 0
    for k in kw:
        if k in _GENERIC_KW:
            continue
        if k in source_norm:
            total += 2 if len(k) >= 6 else 1
    return total


def find_canonical_texts(
    dictee: str, organes: list[str] | None = None, limit: int = 2
) -> list[dict[str, str]]:
    """Formulations de reference du praticien correspondant a la dictee.

    VERROU : sans ``organes`` reconnus dans la bible, retourne [] (aucune
    injection). Retourne au plus ``limit`` entrees, les mieux appariees d'abord.
    """
    chapters = _allowed_chapters(organes or [])
    if not chapters:
        return []
    catalog = _catalog()
    if not catalog:
        return []
    source = normaliser(dictee)
    scored: list[tuple[int, dict[str, object]]] = []
    for entry in catalog:
        if not _entry_in_chapters(entry, chapters):
            continue
        kw = entry.get("kw")
        if not isinstance(kw, list):
            continue
        score = _score([str(k) for k in kw], source)
        if score >= _MIN_SCORE:
            scored.append((score, entry))
    if not scored:
        return []
    scored.sort(key=lambda pair: (-pair[0], len(str(pair[1].get("texte", "")))))
    out: list[dict[str, str]] = []
    seen: set[str] = set()
    for _, entry in scored:
        lesion = str(entry.get("lesion", ""))
        key = normaliser(lesion)
        if key in seen:
            continue
        seen.add(key)
        out.append({
            "lesion": lesion,
            "code": str(entry.get("code", "")),
            "texte": str(entry.get("texte", ""))[:_MAX_TEXTE],
        })
        if len(out) >= limit:
            break
    return out


def build_canonical_block(dictee: str, organes: list[str] | None = None) -> str:
    """Bloc de prompt : formulations de reference du praticien (ou vide)."""
    matches = find_canonical_texts(dictee, organes)
    if not matches:
        return ""
    lignes: list[str] = [
        "════════ FORMULATION DE REFERENCE DU PRATICIEN ════════",
        "Voici comment CE praticien redige habituellement cette (ces) lesion(s),",
        "extrait de sa propre bible. Inspire-toi de son VOCABULAIRE, de sa STRUCTURE",
        "et de son niveau de detail : c'est le style et la densite attendus.",
        "ATTENTION : ce sont des MODELES types, PAS les observations de ce cas.",
        "REGLE STRICTE — NE VA JAMAIS AU-DELA DE (dictee + modele) : n'ecris AUCUN",
        "detail descriptif (cytologie, noyaux, nucleoles, mitoses, architecture...) qui",
        "ne figure NI dans la dictee NI dans le modele ci-dessous. Un element du modele",
        "qui n'est pas dicte et qui doit etre CONSTATE sur ce cas precis (ex une",
        "architecture particuliere) se met en [A COMPLETER: element precis] plutot que",
        "d'etre recopie comme s'il avait ete vu.",
        "",
    ]
    for m in matches:
        code = f" (code {m['code']})" if m["code"] else ""
        lignes.append(f"--- {m['lesion']}{code} :")
        lignes.append(m["texte"])
        lignes.append("")
    return "\n".join(lignes).strip()
