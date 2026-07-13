"""Amorce STT (context_bias Voxtral) pour l'anatomie/cytologie pathologiques.

Voxtral accepte ~100 mots/phrases via le parametre ``context_bias`` : on y place
les termes les plus frequemment mal reconnus en transcription medicale ACP
francophone (marqueurs IHC, eponymes/scores, types histologiques...), pour
amorcer la reconnaissance vocale. Seul point d'entree : ``get_context_bias()``,
consomme par ``transcription.py``.

Les corrections phonetiques et l'expansion d'acronymes sont assurees en aval par
le prompt LLM (voir reports/prompts.py), pas ici.
"""

from __future__ import annotations

# Voxtral accepte max ~100 mots/phrases via le parametre context_bias.
# Termes classes par criticite clinique.
CONTEXT_BIAS_TERMS: list[str] = [
    # Marqueurs IHC (très souvent mal transcrits - priorité 1)
    "TTF1", "ALK", "PD-L1", "Ki67",
    "HER2", "CK7", "CK20", "CK5/6", "CDX2", "p16", "p40", "p63", "p53",
    "GATA3", "PAX8", "SOX10", "Melan-A", "HMB45",
    "AMACR", "P504S", "PSA", "NKX3.1", "ERG",
    "Chromogranine", "Synaptophysine",
    "RE", "RP", "MLH1", "MSH2", "MSH6", "PMS2",
    "BRAF", "KRAS", "NRAS", "EGFR", "ROS1",
    "Desmine", "DOG1", "BCL2", "Calrétinine",
    # Éponymes/Scores (critiques pour le sens clinique)
    "Gleason", "ISUP", "Scarff-Bloom-Richardson", "SBR",
    "Breslow", "Clark", "Fuhrman", "Nottingham",
    "pTNM", "FIGO", "METAVIR",
    # Termes techniques fréquemment mal transcrits (mots simples uniquement)
    "adénocarcinome", "carcinome", "épidermoïde", "urothélial",
    "mélanome", "mésothéliome", "lymphome",
    "acineux", "lépidique", "papillaire", "micropapillaire", "cribriforme",
    "trabéculaire", "mucineux", "desmoplasique",
    "koïlocytes", "dyskératose", "parakératose", "acanthose",
    "stroma", "fibro-hyalin", "myxoïde",
    # Anatomie critique
    "bronchique", "hilaire", "parenchymateuse", "périnerveux",
    "lymphovasculaire", "ganglionnaire",
    # Prélèvements
    "lobectomie", "mastectomie", "prostatectomie",
    "néphrectomie", "colectomie", "gastrectomie",
    "thyroïdectomie", "hystérectomie", "cystectomie",
    # Cytologie LBA
    "sidérophages", "polynucléaires", "neutrophiles", "éosinophiles",
    # Néoplasies intraépithéliales
    "AIN3", "CIN3",
    # Biologie moléculaire
    "FISH", "NGS",
    "IDH1", "ATRX", "H3K27M",
]


def get_context_bias() -> list[str]:
    """Retourne les termes pour le context_bias Voxtral (max ~100).

    Selectionnes parmi les plus frequemment mal reconnus en transcription
    medicale ACP francophone.
    """
    return CONTEXT_BIAS_TERMS
