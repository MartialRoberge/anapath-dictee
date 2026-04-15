"""Classification du type de prelevement anatomopathologique.

Module central de l'architecture : detecte le type de prelevement
depuis le contenu du rapport et expose le contexte clinique qui
conditionne toute la logique en aval (champs obligatoires, codage,
suggestions).

Types de prelevement :
- BIOPSIE : carotte, punch, fragment — question = "qu'est-ce que c'est ?"
- PIECE_OPERATOIRE : organe entier — question = "a quel point c'est grave ?"
- CYTOLOGIE : liquide, LBA, frottis — question = "y a-t-il des cellules anormales ?"
- CURAGE : ganglions isoles — question = "combien sont envahis ?"

Contexte diagnostique :
- BENIN : pas de tumeur, pas de dysplasie
- PRE_CANCEREUX : dysplasie, in situ, AIN, HSIL — PAS infiltrant
- INFILTRANT : carcinome infiltrant, adenocarcinome, melanome — tumeur maligne
"""

from enum import Enum

from text_utils import normaliser as _normaliser


class SpecimenType(str, Enum):
    """Type de prelevement anatomopathologique."""
    BIOPSIE = "biopsie"
    PIECE_OPERATOIRE = "piece_operatoire"
    CYTOLOGIE = "cytologie"
    CURAGE = "curage"
    INDETERMINE = "indetermine"


class DiagnosticContext(str, Enum):
    """Contexte diagnostique du rapport."""
    BENIN = "benin"
    PRE_CANCEREUX = "pre_cancereux"
    INFILTRANT = "infiltrant"
    INDETERMINE = "indetermine"


# ---------------------------------------------------------------------------
# Mots-cles de detection du type de prelevement
# ---------------------------------------------------------------------------

_BIOPSIE_KEYWORDS: list[str] = [
    "biopsie", "biopsique", "biopsies",
    "carotte", "carottes",
    "fragment biopsique", "fragments biopsiques",
    "punch", "punch biopsie",
    "microbiopsie", "macrobiopsie",
    "prelevement biopsique",
    "curetage biopsique",
]

_PIECE_KEYWORDS: list[str] = [
    "piece operatoire", "piece de",
    "tumorectomie", "mastectomie", "lumpectomie",
    "colectomie", "sigmoidectomie", "hemicolectomie",
    "gastrectomie",
    "nephrectomie",
    "prostatectomie",
    "lobectomie", "pneumonectomie", "segmentectomie",
    "thyroidectomie", "lobo-isthmectomie",
    "hysterectomie", "annexectomie",
    "cystectomie",
    "amputation", "amputation abdomino-perineale",
    "resection", "resection anterieure",
    "exerese", "exerese large",
    "orchidectomie",
    "laryngectomie", "pharyngectomie",
    "hepatectomie",
    "duodeno-pancreatectomie", "splenopancreatectomie",
]

_CYTOLOGIE_KEYWORDS: list[str] = [
    "cytologie", "cytologique",
    "lba", "lavage bronchiolo-alveolaire", "lavage broncho-alveolaire",
    "liquide de lavage",
    "frottis",
    "epanchement", "liquide pleural", "liquide peritoneal", "ascite",
    "cytoponction", "ponction",
    "aspiration",
    "urine", "urines",
]

_CURAGE_KEYWORDS: list[str] = [
    "curage", "curage ganglionnaire",
    "evidement", "evidement ganglionnaire",
    "ganglion sentinelle",
]

# ---------------------------------------------------------------------------
# Mots-cles du contexte diagnostique
# ---------------------------------------------------------------------------

_PRE_CANCEREUX_KEYWORDS: list[str] = [
    "ain1", "ain2", "ain3",
    "cin1", "cin2", "cin3",
    "hsil", "lsil",
    "neoplasie intraepitheliale",
    "neoplasie malpighienne intraepitheliale",
    "dysplasie de haut grade",
    "dysplasie de bas grade",
    "dysplasie moderee",
    "dysplasie severe",
    "carcinome in situ",
    "in situ",
    "dcis", "lcis",
    "adenome", "polype adenomateux",
]

_INFILTRANT_KEYWORDS: list[str] = [
    "carcinome infiltrant",
    "carcinome invasif",
    "adenocarcinome infiltrant",
    "adenocarcinome invasif",
    "carcinome epidermoide infiltrant",
    "carcinome canalaire infiltrant",
    "carcinome lobulaire infiltrant",
    "carcinome de type non specifique",
    "melanome malin",
    "melanome invasif",
    "lymphome",
    "sarcome",
    "glioblastome",
    "mesotheliome",
    "tumeur maligne",
    "tumeur infiltrante",
]

_BENIN_KEYWORDS: list[str] = [
    "absence de malignite",
    "absence de dysplasie",
    "pas de malignite",
    "pas de dysplasie",
    "benin", "benigne",
    "hyperplasie",
    "inflammation",
    "inflammatoire",
    "fibrose",
    "metaplasie",
    "tissu normal",
    "pas de lesion",
    "absence de lesion",
    "sans atypie",
    "pas de proliferation tumorale",
    "absence de proliferation tumorale",
]

_NEGATION_PREFIXES: list[str] = [
    "absence de", "pas de", "sans", "il n'est pas",
    "ne montre pas de", "ne trouve pas de",
    "indemne de", "ni de",
]


# ---------------------------------------------------------------------------
# Fonctions utilitaires
# ---------------------------------------------------------------------------


def _contient_hors_negation(texte: str, keywords: list[str]) -> bool:
    """Verifie si un mot-cle est present HORS d'une phrase de negation.

    Verifie TOUTES les occurrences de chaque mot-cle, pas seulement
    la premiere. Si la premiere est niee mais une suivante est affirmee,
    retourne True. Le contexte avant est limite a la phrase courante
    (depuis le dernier point ou debut de ligne).
    """
    for kw in keywords:
        kw_norm: str = _normaliser(kw)
        start: int = 0
        while True:
            pos: int = texte.find(kw_norm, start)
            if pos == -1:
                break
            # Trouver le debut de la phrase courante (dernier point ou newline)
            sentence_start: int = max(
                texte.rfind(".", 0, pos) + 1,
                texte.rfind("\n", 0, pos) + 1,
                0,
            )
            contexte_avant: str = texte[sentence_start:pos]
            est_nie: bool = any(neg in contexte_avant for neg in _NEGATION_PREFIXES)
            if not est_nie:
                return True
            start = pos + 1
    return False


# ---------------------------------------------------------------------------
# Fonctions principales
# ---------------------------------------------------------------------------


def detecter_specimen_type(rapport: str) -> SpecimenType:
    """Detecte le type de prelevement depuis le contenu du rapport.

    Priorite : biopsie/cytologie explicites > piece operatoire > curage >
    defaut piece. Si la dictee ne mentionne PAS explicitement
    "biopsie" ou "cytologie", on presume PIECE_OPERATOIRE (retour
    praticienne : la description macroscopique volumineuse est un
    signal fort de piece operatoire).
    """
    texte: str = _normaliser(rapport)

    # 1. Biopsie explicite (mot-cle biopsie/carotte/punch) — priorite haute
    #    Retour praticienne : si le praticien dit "biopsie de" c'est une biopsie
    for kw in _BIOPSIE_KEYWORDS:
        if _normaliser(kw) in texte:
            return SpecimenType.BIOPSIE

    # 2. Cytologie explicite (LBA, ponction, frottis)
    for kw in _CYTOLOGIE_KEYWORDS:
        if _normaliser(kw) in texte:
            return SpecimenType.CYTOLOGIE

    # 3. Piece operatoire explicite (acte chirurgical nomme)
    for kw in _PIECE_KEYWORDS:
        if _normaliser(kw) in texte:
            return SpecimenType.PIECE_OPERATOIRE

    # 4. Curage ganglionnaire isole
    for kw in _CURAGE_KEYWORDS:
        if _normaliser(kw) in texte:
            return SpecimenType.CURAGE

    # 5. Heuristique macroscopique : description volumineuse avec mesures
    #    en cm ou curages ganglionnaires -> signal piece operatoire
    if _macroscopie_suggere_piece(texte):
        return SpecimenType.PIECE_OPERATOIRE

    # 6. Defaut : PIECE_OPERATOIRE (cf retour praticienne)
    #    "si on ne dit pas 'biopsie de' ou 'cytologie de', partir du
    #    principe que c'est une piece operatoire"
    return SpecimenType.PIECE_OPERATOIRE


def _macroscopie_suggere_piece(texte_normalise: str) -> bool:
    """Indice macroscopique en faveur d'une piece operatoire.

    Signaux : mesures en cm, plusieurs loges ganglionnaires, nombre
    de ganglions examines, mention d'inclusion par blocs multiples.
    """
    import re

    # Mesures en cm type "20 x 19 x 9 cm" ou "18 x 17 x 14 mm" pour un organe
    if re.search(r"\d+\s*[x×]\s*\d+\s*[x×]\s*\d+\s*(cm|mm)", texte_normalise):
        return True

    # Enumeration de ganglions par loges (piece avec curages)
    if re.search(r"\b\d+\s*ganglions?\b", texte_normalise) and "loge" in texte_normalise:
        return True

    return False


def detecter_diagnostic_context(rapport: str) -> DiagnosticContext:
    """Detecte le contexte diagnostique du rapport.

    Priorite : INFILTRANT > PRE_CANCEREUX > BENIN.
    "Absence de carcinome infiltrant" dans un contexte AIN3 =
    PRE_CANCEREUX (pas infiltrant).
    """
    texte: str = _normaliser(rapport)

    # Infiltrant — chercher HORS negation
    if _contient_hors_negation(texte, _INFILTRANT_KEYWORDS):
        return DiagnosticContext.INFILTRANT

    # Pre-cancereux
    for kw in _PRE_CANCEREUX_KEYWORDS:
        if _normaliser(kw) in texte:
            return DiagnosticContext.PRE_CANCEREUX

    # Benin
    for kw in _BENIN_KEYWORDS:
        if _normaliser(kw) in texte:
            return DiagnosticContext.BENIN

    return DiagnosticContext.INDETERMINE


# ---------------------------------------------------------------------------
# Champs applicables par contexte
# ---------------------------------------------------------------------------

# Champs qui ne s'appliquent qu'aux PIECES OPERATOIRES
CHAMPS_PIECE_ONLY: set[str] = {
    "ptnm", "tnm", "staging", "stade", "figo",
    "marge", "limites d'exerese", "limites chirurgicales", "limite", "recoupe",
    "crm", "circonferentielle", "mesorectum", "qualite du mesorectum",
    "ganglion", "curage", "ganglionnaire", "sentinelle",
    "score de regression", "trg",
    "effraction capsulaire", "rupture capsulaire",
    "extension extra", "invasion du muscle", "invasion de la graisse",
    "microsatellitose",
    "taille tumorale", "taille de la tumeur",
}

# Champs qui ne s'appliquent qu'au contexte INFILTRANT (tumeur maligne confirmee)
CHAMPS_INFILTRANT_ONLY: set[str] = {
    "embole", "invasion vasculaire", "invasion lympho",
    "engainement", "perinerveux", "perineural",
    "invasion pleurale",
    "composante in situ",
    "tumour budding",
    "grade sbr", "grade nottingham", "grade fnclcc",
    "grade isup", "grade nucleaire",
    "grade de differenciation", "degre de differenciation",
    "score de gleason", "gleason", "fuhrman",
    "breslow", "clark", "index mitotique",
    "statut her2", "statut re", "statut rp",
    "ki67", "ki-67",
    "pd-l1", "pdl1",
    "msi", "mmr",
    "egfr", "alk", "ros1", "kras", "nras", "braf", "brca",
    "biologie moleculaire",
    # Sous-types tumoraux — pas pertinents si benin/pre-cancereux
    "sous-type", "pattern predominant", "pattern",
    "architecture predominante", "architecture tumorale",
    "type histologique oms",
}

# Champs qui ne s'appliquent qu'aux PIECES (pas aux biopsies)
# meme si la tumeur est infiltrante sur biopsie
CHAMPS_BIOPSIE_EXCLUS: set[str] = {
    "invasion pleurale",
}


def champ_applicable(
    nom_champ: str,
    specimen: SpecimenType,
    contexte: DiagnosticContext,
) -> bool:
    """Determine si un champ est applicable au contexte actuel.

    C'est la fonction centrale de filtrage. Elle est appelee par
    detection_manquantes.py pour chaque champ candidat.
    """
    nom_norm: str = _normaliser(nom_champ)

    # Champs piece operatoire : uniquement si c'est une piece
    for exclu in CHAMPS_PIECE_ONLY:
        if exclu in nom_norm:
            if specimen != SpecimenType.PIECE_OPERATOIRE:
                return False

    # Champs infiltrant : uniquement si contexte infiltrant
    for exclu in CHAMPS_INFILTRANT_ONLY:
        if exclu in nom_norm:
            if contexte != DiagnosticContext.INFILTRANT:
                return False

    # Champs exclus sur biopsie meme si infiltrant
    if specimen == SpecimenType.BIOPSIE:
        for exclu in CHAMPS_BIOPSIE_EXCLUS:
            if exclu in nom_norm:
                return False

    return True
