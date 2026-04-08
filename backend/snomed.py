"""Codage SNOMED CT pour comptes rendus anatomopathologiques.

SNOMED CT (Systematized Nomenclature of Medicine - Clinical Terms)
est la nomenclature internationale de reference pour le codage des
diagnostics en anatomopathologie.

Hierarchies utilisees :
- Body Structure (localisation anatomique)
- Clinical Finding / Morphologic Abnormality (diagnostic)

Ce module fournit une suggestion de codes SNOMED CT depuis le CR
structure et l'organe detecte.
"""


# ---------------------------------------------------------------------------
# Body Structure (localisation anatomique)
# ---------------------------------------------------------------------------

_BODY_STRUCTURES: dict[str, dict[str, str]] = {
    "canal_anal": {"code": "34381000", "display": "Anal canal structure"},
    "bronche": {"code": "955009", "display": "Bronchial structure"},
    "colon_rectum": {"code": "71854001", "display": "Colon structure"},
    "col_uterin": {"code": "71252005", "display": "Cervix uteri structure"},
    "endometre": {"code": "2739003", "display": "Endometrial structure"},
    "estomac": {"code": "69695003", "display": "Stomach structure"},
    "foie": {"code": "10200004", "display": "Liver structure"},
    "melanome": {"code": "39937001", "display": "Skin structure"},
    "oesophage": {"code": "32849002", "display": "Esophageal structure"},
    "ovaire": {"code": "15497006", "display": "Ovarian structure"},
    "pancreas": {"code": "15776009", "display": "Pancreatic structure"},
    "plevre": {"code": "3120008", "display": "Pleural structure"},
    "poumon": {"code": "39607008", "display": "Lung structure"},
    "prostate": {"code": "41216001", "display": "Prostatic structure"},
    "rein": {"code": "64033007", "display": "Kidney structure"},
    "sein": {"code": "76752008", "display": "Breast structure"},
    "snc": {"code": "12738006", "display": "Brain structure"},
    "testicule": {"code": "40689003", "display": "Testis structure"},
    "thyroide": {"code": "69748006", "display": "Thyroid structure"},
    "vessie": {"code": "89837001", "display": "Urinary bladder structure"},
}

# ---------------------------------------------------------------------------
# Clinical Finding / Morphologic Abnormality (diagnostics)
# ---------------------------------------------------------------------------

_MORPHOLOGIES: list[tuple[str, str, list[str]]] = [
    # Lesions pre-cancereuses
    ("65845004", "Neoplasie intraepitheliale de haut grade (HSIL)",
     ["ain3", "hsil", "neoplasie intraepitheliale de haut grade",
      "neoplasie malpighienne intraepitheliale de haut grade",
      "dysplasie de haut grade"]),
    ("285636001", "Neoplasie intraepitheliale de bas grade (LSIL)",
     ["ain1", "lsil", "neoplasie intraepitheliale de bas grade",
      "lesion malpighienne intraepitheliale de bas grade",
      "dysplasie de bas grade"]),

    # Carcinomes
    ("402815007", "Carcinome epidermoide",
     ["carcinome epidermoide", "carcinome malpighien"]),
    ("35917007", "Adenocarcinome",
     ["adenocarcinome"]),
    ("82711006", "Carcinome canalaire infiltrant du sein",
     ["carcinome canalaire infiltrant", "carcinome infiltrant de type non specifique"]),
    ("44782003", "Carcinome lobulaire infiltrant du sein",
     ["carcinome lobulaire infiltrant"]),
    ("254626006", "Adenocarcinome du poumon",
     ["adenocarcinome pulmonaire", "adenocarcinome du poumon",
      "adenocarcinome acineux", "adenocarcinome lepidique"]),
    ("372130007", "Melanome malin",
     ["melanome"]),
    ("93655004", "Carcinome a cellules renales",
     ["carcinome a cellules renales", "carcinome renal"]),

    # Tumeurs non-epitheliales
    ("188725004", "Lymphome",
     ["lymphome"]),
    ("404136000", "Sarcome",
     ["sarcome"]),
    ("393564001", "Glioblastome",
     ["glioblastome"]),

    # Lesions benignes / non-tumorales
    ("76197007", "Hyperplasie",
     ["hyperplasie"]),
    ("23583003", "Inflammation",
     ["inflammation", "inflammatoire"]),
    ("263680009", "Fibrose",
     ["fibrose"]),
    ("4500007", "Metaplasie",
     ["metaplasie"]),

    # Infections
    ("240542006", "Condylome / infection HPV",
     ["condylome", "condylomateuse", "koilocyte", "hpv", "papillomavirus"]),

    # Normal
    ("17621005", "Tissu normal",
     ["absence de lesion", "tissu normal", "absence de malignite",
      "pas de dysplasie"]),
]


from text_utils import normaliser

_NEGATION_MARKERS: list[str] = [
    "absence de", "pas de", "sans", "il n'est pas",
    "ne montre pas de", "ne trouve pas de", "indemne de",
]


def _masquer_negations(texte: str) -> str:
    """Masque les portions de texte en contexte de negation."""
    resultat: str = texte
    for marker in _NEGATION_MARKERS:
        while marker in resultat:
            pos: int = resultat.find(marker)
            end: int = len(resultat)
            for sep in [".", "\n"]:
                sep_pos: int = resultat.find(sep, pos + len(marker))
                if sep_pos != -1 and sep_pos < end:
                    end = sep_pos
            resultat = resultat[:pos] + " " * (end - pos) + resultat[end:]
    return resultat


def suggerer_snomed(rapport: str, organe_detecte: str) -> dict[str, str | dict[str, str]]:
    """Suggere des codes SNOMED CT depuis le rapport et l'organe detecte.

    Utilise le masquage de negations pour eviter de coder
    "absence de carcinome" comme un carcinome.

    Returns:
        Dictionnaire avec :
        - topography : {code, display, system}
        - morphology : {code, display, system}
    """
    rapport_normalise: str = normaliser(rapport)

    # Topographie
    body = _BODY_STRUCTURES.get(organe_detecte)
    topography: dict[str, str] = {
        "code": body["code"] if body else "",
        "display": body["display"] if body else "Non determine",
        "system": "http://snomed.info/sct",
    }

    # Morphologie - chercher du plus specifique au plus generique
    # Masquer les negations pour eviter les faux positifs
    texte_sans_negations: str = _masquer_negations(rapport_normalise)
    morphology: dict[str, str] = {
        "code": "",
        "display": "Non determine",
        "system": "http://snomed.info/sct",
    }
    for code, display, keywords in _MORPHOLOGIES:
        for kw in keywords:
            if kw in texte_sans_negations:
                morphology = {
                    "code": code,
                    "display": display,
                    "system": "http://snomed.info/sct",
                }
                break
        if morphology["code"]:
            break

    return {
        "topography": topography,
        "morphology": morphology,
    }
