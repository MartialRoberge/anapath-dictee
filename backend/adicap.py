"""Codage ADICAP (Association pour le Developpement de l'Informatique
en Cytologie et Anatomie Pathologiques).

Le code ADICAP est le systeme de codage francais obligatoire en
anatomopathologie. Structure : 8 caracteres.

Position 1 : Mode de prelevement (1 car.)
Position 2 : Technique (1 car.)
Positions 3-4 : Organe/topographie (2 car.)
Positions 5-8 : Lesion/morphologie (4 car.)

Ce module fournit :
- Les tables de reference (prelevement, technique, organe, lesion)
- La suggestion automatique du code ADICAP depuis le CR structure
"""

import re

# ---------------------------------------------------------------------------
# Tables de reference ADICAP
# ---------------------------------------------------------------------------

MODES_PRELEVEMENT: dict[str, str] = {
    "B": "Biopsie",
    "C": "Cytologie",
    "P": "Piece operatoire",
    "A": "Autopsie",
    "E": "Extemporane",
    "L": "Liquide",
    "F": "Frottis",
    "G": "Ganglion sentinelle",
    "R": "Recoupes / complements",
    "T": "Curage ganglionnaire",
}

TECHNIQUES: dict[str, str] = {
    "H": "Histologie (paraffine)",
    "E": "Extemporane (congelation)",
    "C": "Cytologie",
    "I": "Immunohistochimie",
    "M": "Biologie moleculaire",
    "F": "Cytologie en milieu liquide",
}

ORGANES: dict[str, str] = {
    "AN": "Canal anal",
    "BR": "Bronche",
    "CO": "Colon",
    "CU": "Col uterin",
    "EN": "Endometre",
    "ES": "Estomac",
    "FO": "Foie",
    "GA": "Ganglion lymphatique",
    "LA": "Larynx / ORL",
    "ME": "Melanome / peau",
    "OE": "Oesophage",
    "OV": "Ovaire",
    "PA": "Pancreas",
    "PE": "Peau",
    "PL": "Plevre",
    "PO": "Poumon",
    "PR": "Prostate",
    "RE": "Rectum",
    "RN": "Rein",
    "SA": "Sarcome / tissu mou",
    "SE": "Sein",
    "SN": "Systeme nerveux central",
    "TE": "Testicule",
    "TH": "Thyroide",
    "VE": "Vessie",
}

# Correspondance organe detecte -> code ADICAP
_ORGANE_TO_CODE: dict[str, str] = {
    "canal_anal": "AN",
    "bronche": "BR",
    "colon_rectum": "CO",
    "col_uterin": "CU",
    "endometre": "EN",
    "estomac": "ES",
    "foie": "FO",
    "ganglion": "GA",
    "orl": "LA",
    "melanome": "ME",
    "oesophage": "OE",
    "ovaire": "OV",
    "pancreas": "PA",
    "peau": "PE",
    "poumon": "PO",
    "prostate": "PR",
    "rectum": "RE",
    "rein": "RN",
    "sarcome": "SA",
    "sein": "SE",
    "snc": "SN",
    "testicule": "TE",
    "thyroide": "TH",
    "vessie": "VE",
}

# Lesions courantes (sous-ensemble des codes morphologiques ADICAP)
LESIONS: dict[str, str] = {
    "0000": "Tissu normal / absence de lesion",
    "0010": "Inflammation non specifique",
    "0020": "Inflammation granulomateuse",
    "0030": "Fibrose",
    "0040": "Hyperplasie",
    "0050": "Metaplasie",
    "0060": "Dysplasie de bas grade",
    "0070": "Dysplasie de haut grade",
    "8000": "Neoplasie, type non precise",
    "8010": "Carcinome, type non precise",
    "8012": "Carcinome a grandes cellules",
    "8020": "Carcinome indifferencie",
    "8041": "Carcinome a petites cellules",
    "8046": "Carcinome neuroendocrine",
    "8050": "Carcinome papillaire",
    "8070": "Carcinome epidermoide",
    "8071": "Carcinome epidermoide keratinisant",
    "8072": "Carcinome epidermoide non keratinisant",
    "8077": "Neoplasie intraepitheliale de haut grade (AIN3/HSIL)",
    "8078": "Neoplasie intraepitheliale de bas grade (AIN1/LSIL)",
    "8140": "Adenocarcinome, type non precise",
    "8141": "Adenocarcinome scirrheux",
    "8144": "Adenocarcinome de type intestinal",
    "8145": "Adenocarcinome de type diffus",
    "8148": "Dysplasie glandulaire de haut grade",
    "8210": "Adenocarcinome en polyp adenomateux",
    "8211": "Adenocarcinome tubuleux",
    "8246": "Tumeur neuroendocrine",
    "8250": "Adenocarcinome lepidique",
    "8253": "Adenocarcinome mucineux",
    "8255": "Adenocarcinome acineux",
    "8260": "Adenocarcinome papillaire",
    "8263": "Adenocarcinome micropapillaire",
    "8310": "Carcinome a cellules claires",
    "8312": "Carcinome a cellules renales, type classique",
    "8317": "Carcinome chromophobe",
    "8320": "Carcinome papillaire du rein",
    "8480": "Adenocarcinome mucineux (colon)",
    "8490": "Carcinome a cellules en bague a chaton",
    "8500": "Carcinome canalaire infiltrant (sein)",
    "8501": "Carcinome comedocarcinome",
    "8507": "Carcinome micropapillaire infiltrant",
    "8520": "Carcinome lobulaire infiltrant",
    "8522": "Carcinome mixte canalaire et lobulaire",
    "8530": "Carcinome inflammatoire",
    "8550": "Carcinome acineux (pancreas)",
    "8720": "Melanome malin",
    "8721": "Melanome nodulaire",
    "8723": "Melanome a extension superficielle",
    "8742": "Melanome lentigineux",
    "8743": "Melanome de Dubreuilh",
    "8800": "Sarcome, type non precise",
    "8890": "Leiomyosarcome",
    "8900": "Rhabdomyosarcome",
    "9050": "Mesotheliome",
    "9380": "Gliome",
    "9440": "Glioblastome",
    "9590": "Lymphome, type non precise",
    "9650": "Lymphome de Hodgkin",
    "9680": "Lymphome diffus a grandes cellules B",
    "9690": "Lymphome folliculaire",
    "9699": "Lymphome de la zone marginale",
    "9702": "Lymphome T peripherique",
    "9823": "Leucemie lymphoide chronique",
}


# ---------------------------------------------------------------------------
# Mots-cles pour detection du mode de prelevement
# ---------------------------------------------------------------------------

_PRELEVEMENT_KEYWORDS: dict[str, list[str]] = {
    "B": ["biopsie", "biopsique", "carotte", "fragment", "punch", "microbiopsie", "macrobiopsie"],
    "P": ["piece operatoire", "piece", "tumorectomie", "mastectomie", "colectomie",
          "gastrectomie", "nephrectomie", "prostatectomie", "lobectomie", "pneumonectomie",
          "thyroidectomie", "hysterectomie", "amputation", "exerese"],
    "C": ["cytologie", "frottis", "liquide", "epanchement", "lavage", "lba",
          "cytoponction", "aspiration"],
    "G": ["ganglion sentinelle", "sentinelle"],
    "T": ["curage", "curage ganglionnaire", "evidement"],
    "E": ["extemporane", "congelation"],
}

_TECHNIQUE_KEYWORDS: dict[str, list[str]] = {
    "H": ["paraffine", "histologie", "histologique", "coupe", "inclusion"],
    "E": ["extemporane", "congelation", "coupe a congelation"],
    "C": ["cytologie", "cytocentrifugation", "frottis", "lba"],
    "I": ["immunohistochimie", "ihc", "immunomarquage"],
    "M": ["biologie moleculaire", "sequencage", "ngs", "fish", "pcr"],
}


# ---------------------------------------------------------------------------
# Fonctions de detection
# ---------------------------------------------------------------------------


def _normaliser(texte: str) -> str:
    """Normalise le texte pour la recherche."""
    resultat: str = texte.lower()
    remplacements: dict[str, str] = {
        "é": "e", "è": "e", "ê": "e", "ë": "e",
        "à": "a", "â": "a", "ô": "o", "ù": "u",
        "û": "u", "î": "i", "ï": "i", "ç": "c",
    }
    for accent, remplacement in remplacements.items():
        resultat = resultat.replace(accent, remplacement)
    return resultat


def _detecter_prelevement(rapport_normalise: str) -> str:
    """Detecte le mode de prelevement depuis le texte du rapport."""
    for code, keywords in _PRELEVEMENT_KEYWORDS.items():
        for kw in keywords:
            if kw in rapport_normalise:
                return code
    return "B"


def _detecter_technique(rapport_normalise: str) -> str:
    """Detecte la technique depuis le texte du rapport."""
    for code, keywords in _TECHNIQUE_KEYWORDS.items():
        for kw in keywords:
            if kw in rapport_normalise:
                return code
    return "H"


def _detecter_code_organe(organe_detecte: str) -> str:
    """Convertit l'organe detecte en code ADICAP 2 caracteres."""
    return _ORGANE_TO_CODE.get(organe_detecte, "XX")


def _detecter_lesion(rapport_normalise: str) -> str:
    """Detecte le code lesion ADICAP depuis le diagnostic."""
    # Chercher du plus specifique au plus generique
    lesion_keywords: list[tuple[str, list[str]]] = [
        # Neoplasies intraepitheliales
        ("8077", ["ain3", "hsil", "neoplasie intraepitheliale de haut grade",
                  "neoplasie malpighienne intraepitheliale de haut grade",
                  "dysplasie de haut grade"]),
        ("8078", ["ain1", "lsil", "neoplasie intraepitheliale de bas grade",
                  "lesion malpighienne intraepitheliale de bas grade"]),
        # Carcinomes specifiques
        ("8500", ["carcinome canalaire infiltrant", "carcinome infiltrant de type non specifique"]),
        ("8520", ["carcinome lobulaire infiltrant", "lobulaire infiltrant"]),
        ("8070", ["carcinome epidermoide"]),
        ("8140", ["adenocarcinome"]),
        ("8255", ["adenocarcinome acineux", "acineuse"]),
        ("8250", ["adenocarcinome lepidique", "lepidique"]),
        ("8260", ["adenocarcinome papillaire", "papillaire"]),
        ("8253", ["adenocarcinome mucineux", "mucineux"]),
        ("8263", ["adenocarcinome micropapillaire", "micropapillaire"]),
        ("8720", ["melanome"]),
        ("8800", ["sarcome"]),
        ("9590", ["lymphome"]),
        ("9680", ["lymphome diffus a grandes cellules"]),
        # Generiques
        ("8010", ["carcinome"]),
        ("8000", ["neoplasie", "tumeur maligne"]),
        # Non-tumoraux
        ("0040", ["hyperplasie"]),
        ("0010", ["inflammation", "inflammatoire"]),
        ("0030", ["fibrose"]),
        ("0050", ["metaplasie"]),
        ("0000", ["absence de lesion", "tissu normal", "pas de dysplasie",
                  "absence de malignite"]),
    ]

    for code, keywords in lesion_keywords:
        for kw in keywords:
            if kw in rapport_normalise:
                return code

    return "0000"


# ---------------------------------------------------------------------------
# Fonction principale
# ---------------------------------------------------------------------------


def suggerer_adicap(rapport: str, organe_detecte: str) -> dict[str, str]:
    """Suggere un code ADICAP depuis le rapport structure et l'organe detecte.

    Returns:
        Dictionnaire avec :
        - code : le code ADICAP complet (8 car.)
        - prelevement : description du mode de prelevement
        - technique : description de la technique
        - organe : description de l'organe
        - lesion : description de la lesion
        - prelevement_code, technique_code, organe_code, lesion_code : codes bruts
    """
    rapport_normalise: str = _normaliser(rapport)

    prelevement_code: str = _detecter_prelevement(rapport_normalise)
    technique_code: str = _detecter_technique(rapport_normalise)
    organe_code: str = _detecter_code_organe(organe_detecte)
    lesion_code: str = _detecter_lesion(rapport_normalise)

    code_complet: str = f"{prelevement_code}{technique_code}.{organe_code}.{lesion_code}"

    return {
        "code": code_complet,
        "prelevement": MODES_PRELEVEMENT.get(prelevement_code, "Inconnu"),
        "prelevement_code": prelevement_code,
        "technique": TECHNIQUES.get(technique_code, "Inconnue"),
        "technique_code": technique_code,
        "organe": ORGANES.get(organe_code, "Non determine"),
        "organe_code": organe_code,
        "lesion": LESIONS.get(lesion_code, "Non determinee"),
        "lesion_code": lesion_code,
    }
