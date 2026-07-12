"""Codage ADICAP conforme, base sur la bible de codes de l'utilisateur.

Le code ADICAP fait 8 caracteres :
  pos 1   : mode de prelevement (D1)
  pos 2   : type de technique  (D2)
  pos 3-4 : organe / topographie (D3, code mnemonique 2 lettres)
  pos 5-8 : lesion (D4 non tumoral / D5 tumoral / D6, 4 caracteres)

Principe de securite (exigence produit) : ne JAMAIS emettre un code lesionnel
faux. Le module code de facon DETERMINISTE les parties objectives (prelevement,
technique, organe) et ne propose un code lesionnel que si le diagnostic
correspond de facon nette a une entree validee de la bible ; sinon il DIFFERE
(lesion "____") et le signale. Ce n'est pas de l'interpretation : c'est un
rappel de codification que le pathologiste valide.

Source de verite : ``data/adicap_bible.json`` (extrait de la bible de codes
fournie par l'utilisateur), complete par les codes organe D3 officiels.
"""

from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from text_utils import normaliser

_DATA_PATH: Path = Path(__file__).resolve().parent / "data" / "adicap_bible.json"

# ---------------------------------------------------------------------------
# Dictionnaires D1 / D2 (officiels, thesaurus ADICAP v5-04 2009)
# ---------------------------------------------------------------------------

MODES_PRELEVEMENT: dict[str, str] = {
    "B": "Biopsie chirurgicale",
    "O": "Piece operatoire (exerese complete)",
    "I": "Exerese partielle de l'organe",
    "K": "Curetage / resection endoscopique",
    "P": "Ponction-biopsie non guidee",
    "C": "Cytoponction non guidee",
    "G": "Cytoponction guidee par imagerie",
    "L": "Liquide (epanchement, urine, LCR, kyste)",
    "R": "Liquide de rincage / lavage d'organe creux",
    "F": "Frottis (raclage, brossage)",
}

TECHNIQUES: dict[str, str] = {
    "H": "Histologie et cytologie par inclusion",
    "C": "Cytologie par etalement",
    "E": "Extemporane",
    "I": "Immunohistochimie",
    "M": "Macroscopie",
    "Y": "Biologie moleculaire (hybridation in situ...)",
    "S": "Coloration speciale",
}

# ---------------------------------------------------------------------------
# D3 — organe detecte (nom applicatif) -> code ADICAP 2 lettres.
# Codes derives de la bible utilisateur (validee) + codes officiels.
# Un organe absent -> None -> le codeur differe l'organe ("XX") et le signale.
# ---------------------------------------------------------------------------

ORGANE_APP_TO_D3: dict[str, str | None] = {
    # Thorax (respiratoire)
    "poumon": "RP",
    "bronche": "RB",
    "plevre": "RS",
    # Digestif
    "colon_rectum": "DC",
    "rectum": "DR",
    "estomac": "DE",
    "oesophage": "DO",
    "duodenum": "DD",
    "appendice": "DA",
    "canal_anal": "DQ",
    "anus": "DQ",
    "foie": "FF",
    "vesicule_biliaire": "FV",
    "pancreas": "FP",
    # Uro / genital masculin
    "prostate": "HP",
    "testicule": "HT",
    "vessie": "UV",
    "rein": "UR",
    # Gyneco
    "ovaire": "GO",
    "endometre": "GU",
    "col_uterin": "GC",
    "vulve": "GV",
    "vagin": "GG",
    # Endocrine
    "thyroide": "ET",
    "surrenale": "ES",
    "parathyroide": "EP",
    # Hemato
    "ganglion": "SG",
    "lymphome": "SG",
    "moelle_osseuse": "SM",
    "rate": "SR",
    # Peau / melanome (teguments)
    "melanome": "OT",
    "peau": "OT",
    # ORL / tete et cou
    "orl_tete_cou": "AL",
    "larynx": "AL",
    "pharynx": "AP",
    "amygdale": "AA",
    "glande_salivaire": "BA",
    # Sein
    "sein": "GS",
    # Tissus mous / os
    "sarcome": "TC",
    "os": "LO",
    # SNC
    "systeme_nerveux_central": "NH",
    "meninge": "NM",
    # Sens
    "oeil": "OE",
}

# Libelle d'organe AFFICHE (anatomique, correct) — decouple des etiquettes de la
# bible qui sont parfois specifiques a une lesion (ex GS n'a que "Gynecomastie"
# alors que GS = glande mammaire). Evite d'afficher un organe absurde au medecin.
ORGANE_DISPLAY: dict[str, str] = {
    "poumon": "Poumon", "bronche": "Bronche", "plevre": "Plevre",
    "colon_rectum": "Colon-rectum", "rectum": "Rectum", "estomac": "Estomac",
    "oesophage": "Oesophage", "duodenum": "Duodenum", "appendice": "Appendice",
    "canal_anal": "Canal anal / anus", "anus": "Canal anal / anus", "foie": "Foie",
    "vesicule_biliaire": "Vesicule biliaire", "pancreas": "Pancreas",
    "prostate": "Prostate", "testicule": "Testicule", "vessie": "Vessie",
    "rein": "Rein", "ovaire": "Ovaire", "endometre": "Endometre / uterus",
    "col_uterin": "Col uterin", "vulve": "Vulve", "vagin": "Vagin",
    "thyroide": "Thyroide", "surrenale": "Surrenale", "parathyroide": "Parathyroide",
    "ganglion": "Ganglion lymphatique", "lymphome": "Ganglion lymphatique",
    "moelle_osseuse": "Moelle osseuse", "rate": "Rate",
    "melanome": "Peau", "peau": "Peau",
    "orl_tete_cou": "Tete et cou (ORL)", "larynx": "Larynx", "pharynx": "Pharynx",
    "amygdale": "Amygdale", "glande_salivaire": "Glande salivaire",
    "sein": "Sein", "sarcome": "Tissus mous", "os": "Os / articulation",
    "systeme_nerveux_central": "Systeme nerveux central", "meninge": "Meninge",
    "oeil": "Oeil",
}

# Code lesionnel differe (non code par securite).
LESION_DIFFEREE: str = "____"


@dataclass(frozen=True, slots=True)
class LesionEntry:
    organ_code: str | None
    lesion: str
    lesion_code: str
    kw: tuple[str, ...]


@dataclass(slots=True)
class AdicapResult:
    code: str
    prelevement: str
    prelevement_code: str
    technique: str
    technique_code: str
    organe: str
    organe_code: str
    lesion: str
    lesion_code: str
    confidence: str  # "haute" | "organe_seul" | "aucune"
    note: str = ""

    def as_dict(self) -> dict[str, str]:
        return {
            "code": self.code,
            "prelevement": self.prelevement,
            "prelevement_code": self.prelevement_code,
            "technique": self.technique,
            "technique_code": self.technique_code,
            "organe": self.organe,
            "organe_code": self.organe_code,
            "lesion": self.lesion,
            "lesion_code": self.lesion_code,
            "confidence": self.confidence,
            "note": self.note,
        }


# Table lesionnelle OFFICIELLE (thesaurus ADICAP v5-04, codes D5 tumoraux et D4
# non tumoraux verifies). D5 = type histologique, independant de l'organe (porte
# par le D3). Fusionnee au catalogue de la bible.
_OFFICIAL_LESIONS: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    # -- tumoral (D5) --
    ("A7B2", "Adenocarcinome canalaire infiltrant", ("canalaire", "infiltrant")),
    ("A7B1", "Adenocarcinome lobulaire infiltrant", ("lobulaire", "infiltrant")),
    ("A5B1", "Adenocarcinome lobulaire in situ", ("lobulaire", "situ")),
    ("A5A0", "Adenocarcinome in situ (SAI)", ("adenocarcinome", "situ")),
    ("A7D0", "Adenocarcinome papillaire (SAI)", ("papillaire", "carcinome")),
    ("A7K2", "Adenocarcinome a cellules claires", ("cellules", "claires")),
    ("A7A0", "Adenocarcinome invasif (SAI)", ("adenocarcinome",)),
    ("E5T0", "Carcinome epidermoide in situ (SAI)", ("epidermoide", "situ")),
    ("E7T0", "Carcinome epidermoide invasif (SAI)", ("epidermoide",)),
    ("U7A0", "Carcinome urothelial infiltrant (SAI)", ("urothelial",)),
    ("U7A0", "Carcinome transitionnel infiltrant", ("transitionnel", "infiltrant")),
    ("M5A0", "Melanome malin in situ (SAI)", ("melanome", "situ")),
    ("M7A0", "Melanome malin (SAI)", ("melanome",)),
    ("B7A0", "Carcinome basocellulaire (SAI)", ("basocellulaire",)),
    ("S7X0", "Tumeur maligne a cellules de Merkel", ("merkel",)),
    ("J7G1", "Lymphome B diffus a grandes cellules (SAI)",
     ("lymphome", "diffus", "grandes", "cellules")),
    ("A0A0", "Adenome - polyadenome (SAI)", ("adenome",)),
    # -- non tumoral (D4) --
    ("7600", "Inflammation subaigue et chronique (SAI)", ("inflammation", "chronique")),
    ("7000", "Inflammation aigue commune (SAI)", ("inflammation", "aigue")),
    ("6418", "Metaplasie malpighienne", ("metaplasie", "malpighienne")),
    ("6416", "Metaplasie intestinale", ("metaplasie", "intestinale")),
    ("6400", "Metaplasie (SAI)", ("metaplasie",)),
    ("6800", "Dysplasie ou hyperplasie atypique (SAI)", ("dysplasie",)),
    ("6700", "Hyperplasie (SAI)", ("hyperplasie",)),
    ("0000", "Organe / tissu normal", ("normal", "particularite")),
)


@lru_cache(maxsize=1)
def _load_reference() -> tuple[dict[str, dict[str, list[str]]], list[LesionEntry]]:
    raw = json.loads(_DATA_PATH.read_text(encoding="utf-8"))
    catalog = [
        LesionEntry(
            organ_code=e.get("organ_code"),
            lesion=e["lesion"],
            lesion_code=e["lesion_code"],
            kw=tuple(e["kw"]),
        )
        for e in raw["lesion_catalog"]
    ]
    # Supplement officiel (organe-independant : organ_code None).
    for code, label, kw in _OFFICIAL_LESIONS:
        catalog.append(
            LesionEntry(organ_code=None, lesion=label, lesion_code=code, kw=kw)
        )
    return raw["organ_codes"], catalog


def _strip_accents(s: str) -> str:
    return (
        unicodedata.normalize("NFD", s)
        .encode("ascii", "ignore")
        .decode("ascii")
        .lower()
    )


# ---------------------------------------------------------------------------
# Detection prelevement / technique
# ---------------------------------------------------------------------------

_PRELEVEMENT_KEYWORDS: dict[str, list[str]] = {
    "K": ["resection transurethrale", "rtuv", "rtup", "copeaux", "resection endoscopique",
          "polypectomie", "mucosectomie", "curetage"],
    "O": ["piece operatoire", "piece de", "tumorectomie", "mastectomie", "colectomie",
          "gastrectomie", "nephrectomie", "prostatectomie", "lobectomie",
          "pneumonectomie", "thyroidectomie", "hysterectomie", "amputation",
          "exerese", "resection", "conisation", "segmentectomie", "duodeno-pancreatectomie"],
    "G": ["cytoponction guidee", "sous echographie", "ec- guidee"],
    "C": ["cytoponction", "aspiration", "apposition"],
    "L": ["liquide", "epanchement", "lba", "ascite", "pleural", "lavage"],
    "F": ["frottis", "fcu"],
    "B": ["biopsie", "biopsique", "carotte", "punch", "microbiopsie", "macrobiopsie",
          "fragment"],
}

_TECHNIQUE_KEYWORDS: dict[str, list[str]] = {
    "E": ["extemporane", "congelation"],
    "C": ["cytologie", "cytocentrifugation", "etalement", "cytoponction"],
    "Y": ["biologie moleculaire", "sequencage", "ngs", "fish", "hybridation", "pcr", "idylla"],
    "I": ["immunohistochimie", "immunomarquage"],
    "H": ["paraffine", "histolog", "inclusion", "coupe"],
}


def _detecter_prelevement(texte: str) -> str:
    for code, kws in _PRELEVEMENT_KEYWORDS.items():
        if any(k in texte for k in kws):
            return code
    return "B"


def _detecter_technique(texte: str) -> str:
    for code, kws in _TECHNIQUE_KEYWORDS.items():
        if any(k in texte for k in kws):
            return code
    return "H"


# ---------------------------------------------------------------------------
# Masquage des negations (ne pas coder "absence de carcinome")
# ---------------------------------------------------------------------------

_NEGATION_MARKERS: tuple[str, ...] = (
    "absence de", "pas de", "sans ", "il n'est pas", "ne montre pas de",
    "ne trouve pas de", "indemne de", "il n'y a pas",
)


def _masquer_negations(texte: str) -> str:
    resultat = texte
    for marker in _NEGATION_MARKERS:
        while marker in resultat:
            pos = resultat.find(marker)
            end = len(resultat)
            for sep in (".", "\n", ";"):
                sp = resultat.find(sep, pos + len(marker))
                if sp != -1 and sp < end:
                    end = sp
            resultat = resultat[:pos] + " " * (end - pos) + resultat[end:]
    return resultat


# ---------------------------------------------------------------------------
# Matching lesionnel sur la bible
# ---------------------------------------------------------------------------

_TOKEN_RE = re.compile(r"[a-z0-9]+")
_STOP = {"de", "la", "le", "les", "des", "un", "une", "du", "et", "en", "sur",
         "avec", "sans", "pour", "non", "type", "avec"}


def _tokens(texte: str) -> set[str]:
    return {t for t in _TOKEN_RE.findall(_strip_accents(texte)) if len(t) > 2 and t not in _STOP}


def _match_lesion(
    diagnostic: str, organ_code: str | None, catalog: list[LesionEntry]
) -> tuple[LesionEntry | None, float]:
    """Retourne la meilleure entree lesionnelle + score de confiance [0..1].

    Filtre par organe si connu. Score = recouvrement des mots-cles de l'entree
    presents dans le diagnostic. On exige un recouvrement fort ET une avance
    nette sur le 2e candidat pour eviter toute ambiguite (sinon on differe).
    """
    diag_tokens = _tokens(diagnostic)
    if not diag_tokens:
        return None, 0.0

    scored: list[tuple[float, LesionEntry]] = []
    for entry in catalog:
        if organ_code and entry.organ_code and entry.organ_code != organ_code:
            continue
        ekw = set(entry.kw)
        if not ekw:
            continue
        overlap = len(ekw & diag_tokens)
        if overlap == 0:
            continue
        # score = fraction des mots-cles de l'entree retrouves
        score = overlap / len(ekw)
        # bonus si tous les mots-cles de l'entree sont presents
        if overlap == len(ekw):
            score += 0.25
        scored.append((score, entry))

    if not scored:
        return None, 0.0
    scored.sort(key=lambda x: x[0], reverse=True)
    best_score, best = scored[0]
    second = scored[1][0] if len(scored) > 1 else 0.0
    # Confiance haute : score fort et avance nette (ou match unique).
    if best_score >= 0.6 and (best_score - second >= 0.2 or len(scored) == 1):
        return best, min(best_score, 1.0)
    return None, best_score


# ---------------------------------------------------------------------------
# Fonction principale
# ---------------------------------------------------------------------------


def _extraire_diagnostic(rapport: str) -> str:
    """Isole la conclusion / le diagnostic (partie a coder) si reperable."""
    low = rapport.lower()
    idx = low.rfind("conclusion")
    if idx != -1:
        return rapport[idx:]
    return rapport


def suggerer_adicap(rapport: str, organe_detecte: str) -> dict[str, str]:
    """Suggere un code ADICAP conforme depuis le rapport et l'organe detecte.

    Emet un code lesionnel uniquement si la correspondance est nette ; sinon
    differe la lesion ("____") et l'indique dans ``note`` / ``confidence``.
    """
    from organ_utils import canonical_organ

    _organ_codes, catalog = _load_reference()
    texte_norm = normaliser(rapport)
    diagnostic = _masquer_negations(normaliser(_extraire_diagnostic(rapport)))

    organe_canon = canonical_organ(organe_detecte, rapport)
    prelevement_code = _detecter_prelevement(texte_norm)
    technique_code = _detecter_technique(texte_norm)
    organe_code = ORGANE_APP_TO_D3.get(organe_canon)

    entry, _ = _match_lesion(diagnostic, organe_code, catalog)

    if organe_code is None:
        organe_code_out = "XX"
        organe_label = "Organe a preciser (code D3 non disponible)"
    else:
        organe_code_out = organe_code
        # Libelle anatomique correct en priorite ; la bible n'est qu'un fallback.
        organe_label = ORGANE_DISPLAY.get(organe_canon) or organe_detecte

    if entry is not None:
        lesion_code = entry.lesion_code
        lesion_label = entry.lesion
        confidence = "haute"
        note = ""
    else:
        lesion_code = LESION_DIFFEREE
        lesion_label = "Lesion a preciser (pas de correspondance certaine)"
        confidence = "organe_seul" if organe_code else "aucune"
        note = (
            "Code lesionnel differe : le diagnostic ne correspond pas de facon "
            "certaine a une entree validee. A completer par le pathologiste."
        )

    code_complet = f"{prelevement_code}{technique_code}{organe_code_out}{lesion_code}"

    result = AdicapResult(
        code=code_complet,
        prelevement=MODES_PRELEVEMENT.get(prelevement_code, "Inconnu"),
        prelevement_code=prelevement_code,
        technique=TECHNIQUES.get(technique_code, "Inconnue"),
        technique_code=technique_code,
        organe=organe_label,
        organe_code=organe_code_out,
        lesion=lesion_label,
        lesion_code=lesion_code,
        confidence=confidence,
        note=note,
    )
    return result.as_dict()
