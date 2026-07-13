"""Normalisation du nom d'organe libre -> identifiant canonique.

Le LLM renvoie un organe en texte libre ("canal anal", "colon", "thyroide").
La codification (ADICAP/SNOMED) indexe sur des identifiants canoniques
("canal_anal", "colon_rectum", "thyroide"). Ce module fait le pont, avec repli
sur la detection multi-organes du rapport (meme moteur que la generation).
"""

from __future__ import annotations

from text_utils import normaliser

# Alias texte libre -> identifiant canonique (templates_organes / codification).
_ALIASES: dict[str, str] = {
    "poumon": "poumon", "pulmonaire": "poumon", "bronche": "bronche",
    "plevre": "plevre", "plevral": "plevre",
    "colon": "colon_rectum", "côlon": "colon_rectum", "colique": "colon_rectum",
    "rectum": "rectum", "colon rectum": "colon_rectum", "colorectal": "colon_rectum",
    "estomac": "estomac", "gastrique": "estomac",
    "oesophage": "oesophage", "œsophage": "oesophage",
    "duodenum": "duodenum",
    "anus": "canal_anal", "canal anal": "canal_anal", "marge anale": "canal_anal",
    "appendice": "appendice", "foie": "foie", "hepatique": "foie",
    "vesicule": "vesicule_biliaire", "vesicule biliaire": "vesicule_biliaire",
    "pancreas": "pancreas",
    "prostate": "prostate", "prostatique": "prostate",
    "testicule": "testicule", "vessie": "vessie", "urothelial": "vessie",
    "rein": "rein", "renal": "rein",
    "ovaire": "ovaire", "endometre": "endometre", "uterus": "endometre",
    "col uterin": "col_uterin", "col": "col_uterin", "cervix": "col_uterin",
    "vulve": "vulve", "vagin": "vagin",
    "thyroide": "thyroide", "thyroidien": "thyroide",
    "surrenale": "surrenale", "parathyroide": "parathyroide",
    "ganglion": "ganglion", "ganglionnaire": "ganglion",
    "lymphome": "lymphome", "moelle": "moelle_osseuse", "rate": "rate",
    "melanome": "melanome", "peau": "peau", "cutane": "peau", "cutanee": "peau",
    "larynx": "larynx", "amygdale": "amygdale", "orl": "orl_tete_cou",
    "sein": "sein", "mammaire": "sein",
    "sarcome": "sarcome", "os": "os", "osseux": "os",
    "cerveau": "systeme_nerveux_central", "meninge": "meninge",
    "snc": "systeme_nerveux_central",
    "oeil": "oeil", "œil": "oeil",
}


def _strip(s: str) -> str:
    return normaliser(s or "").strip()


def canonical_organ(organe_detecte: str, rapport: str = "") -> str:
    """Retourne l'identifiant canonique de l'organe.

    1. Alias direct sur le texte libre fourni.
    2. Sinon, detection multi-organes sur le rapport (1er organe).
    3. Sinon, renvoie le texte normalise tel quel.
    """
    raw = _strip(organe_detecte)
    if raw in _ALIASES:
        return _ALIASES[raw]
    # underscore form directe (deja canonique)
    canon_forms = set(_ALIASES.values())
    if raw.replace(" ", "_") in canon_forms:
        return raw.replace(" ", "_")

    if rapport.strip():
        try:
            from reports.knowledge import detect_organs

            organs = detect_organs(rapport)
            if organs:
                return organs[0].organe
        except Exception:  # pragma: no cover - robustesse
            pass
    return raw.replace(" ", "_")
