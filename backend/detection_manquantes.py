"""Detection des donnees obligatoires manquantes dans un compte-rendu.

Architecture :
1. specimen_type.py detecte le type de prelevement et le contexte diagnostique
2. Ce module utilise ce contexte pour filtrer les champs pertinents
3. Deux sources de detection :
   - Marqueurs [A COMPLETER: xxx] inseres par le LLM (source primaire)
   - Verification par template organe (source secondaire)

Le filtrage est strict : une biopsie ne suggerera quasi rien (juste le
type histologique), une piece operatoire suggerera tout le panel pronostique.
"""

import re

from models import DonneeManquante
from templates_organes import get_champs_obligatoires, ChampObligatoire
from specimen_type import (
    SpecimenType,
    DiagnosticContext,
    detecter_specimen_type,
    detecter_diagnostic_context,
    champ_applicable,
)

# ---------------------------------------------------------------------------
# Patterns et constantes
# ---------------------------------------------------------------------------

# Pattern pour detecter les marqueurs [A COMPLETER: xxx] dans le rapport
_PATTERN_A_COMPLETER: re.Pattern[str] = re.compile(
    r"\[A COMPLETER\s*:\s*([^\]]+)\]", re.IGNORECASE
)

# Sections connues et leur correspondance dans le rapport
_SECTIONS_MAPPING: dict[str, list[str]] = {
    "macroscopie": ["macroscopie", "macro", "examen macroscopique"],
    "microscopie": [
        "microscopie",
        "micro",
        "etude histologique",
        "histologie",
        "etude cytologique",
        "cytologie",
    ],
    "ihc": [
        "immunomarquage",
        "immunohistochimie",
        "ihc",
        "anticorps",
    ],
    "conclusion": ["conclusion"],
    "biologie_moleculaire": [
        "biologie moleculaire",
        "biologie moléculaire",
        "analyse moleculaire",
        "sequencage",
        "NGS",
        "FISH",
        "CISH",
    ],
}

# ---------------------------------------------------------------------------
# Mots-cles pour determiner le contexte tumoral vs non-tumoral
# ---------------------------------------------------------------------------

# Mots-cles tumoraux positifs : des termes diagnostiques specifiques qui,
# lorsqu'ils apparaissent EN DEHORS d'une phrase de negation, indiquent
# la presence d'une tumeur.
_MOTS_CLES_TUMEUR: list[str] = [
    "carcinome",
    "adenocarcinome",
    "neoplasie",
    "neoplasique",
    "melanome",
    "lymphome",
    "sarcome",
    "gliome",
    "glioblastome",
    "meningiome",
    "seminome",
    "choriocarcinome",
    "carcinome in situ",
    "dysplasie de haut grade",
    "lesion de haut grade",
    "blastome",
    "myelome",
    "leucemie",
]

# Mots-cles tumoraux AMBIGUS : termes qui peuvent apparaitre aussi bien
# dans un contexte tumoral affirmatif ("tumeur infiltrante") que dans
# une negation ("pas de proliferation tumorale"). Ils ne comptent comme
# tumoraux QUE s'ils apparaissent au moins une fois hors negation.
_MOTS_CLES_TUMEUR_AMBIGUS: list[str] = [
    "tumeur",
    "tumoral",
    "tumorale",
    "infiltrant",
    "infiltrante",
    "malin",
    "maligne",
    "malignite",
    "cancer",
    "cancereux",
    "metastase",
    "metastatique",
    "proliferation tumorale",
    "cellules tumorales",
    "cellules malignes",
    "cellules neoplasiques",
]

# Phrases de negation : lorsqu'un mot-cle tumoral ambigu n'apparait que
# dans l'une de ces phrases, il est considere comme NIE et ne compte
# pas comme indicateur de contexte tumoral.
_PHRASES_NEGATION: list[str] = [
    "pas de proliferation tumorale",
    "absence de proliferation tumorale",
    "sans proliferation tumorale",
    "pas de tumeur",
    "absence de tumeur",
    "sans tumeur",
    "pas de malignite",
    "absence de malignite",
    "sans signe de malignite",
    "sans malignite",
    "pas de signe de malignite",
    "pas de cellule tumorale",
    "absence de cellule tumorale",
    "sans cellule tumorale",
    "pas de cellules tumorales",
    "absence de cellules tumorales",
    "sans cellules tumorales",
    "pas de cellules malignes",
    "absence de cellules malignes",
    "sans cellules malignes",
    "pas de cellule maligne",
    "absence de cellule maligne",
    "pas de cellules neoplasiques",
    "absence de cellules neoplasiques",
    "sans cellules neoplasiques",
    "pas de caractere infiltrant",
    "sans caractere infiltrant",
    "pas de metastase",
    "absence de metastase",
    "sans metastase",
    "pas de cancer",
    "absence de cancer",
    "pas de lesion tumorale",
    "absence de lesion tumorale",
    "sans lesion tumorale",
    "pas d'aspect tumoral",
    "sans aspect tumoral",
    "pas de processus tumoral",
    "absence de processus tumoral",
    "sans processus tumoral",
    "pas de caractere malin",
    "sans caractere malin",
    "absence de caractere malin",
]

# ---------------------------------------------------------------------------
# Champs qui ne doivent PAS etre signales pour les rapports non-tumoraux.
# La correspondance se fait par sous-chaine normalisee dans le nom du champ.
# ---------------------------------------------------------------------------

_CHAMPS_EXCLUS_NON_TUMEUR: list[str] = [
    # pTNM / staging
    "ptnm",
    "tnm",
    "staging",
    "stade",
    "figo",
    "ann arbor",
    "lugano",
    # Marges
    "marge",
    "limites d'exerese",
    "limites chirurgicales",
    "limite",
    "recoupe",
    # Ganglions
    "ganglion",
    "curage",
    "ganglionnaire",
    # Emboles / invasion vasculaire
    "embole",
    "invasion vasculaire",
    "invasion lympho",
    # Engainements perinerveux
    "engainement",
    "perinerveux",
    "perineural",
    # Grade de differentiation / scores specifiques
    "grade sbr",
    "grade nottingham",
    "grade fnclcc",
    "grade figo",
    "grade isup",
    "grade nucleaire",
    "grade de differenciation",
    "degre de differenciation",
    "score de gleason",
    "gleason",
    "fuhrman",
    "breslow",
    "clark",
    "index mitotique",
    # Taille tumorale
    "taille tumorale",
    "taille de la tumeur",
    # Type histologique tumoral / sous-types
    "type histologique",
    "sous-type",
    "pattern predominant",
    "architecture tumorale",
    # IHC tumorale et biologie moleculaire
    "pd-l1",
    "pdl1",
    "pd-l1 (tps)",
    "statut her2",
    "statut re",
    "statut rp",
    "ki67",
    "ki-67",
    "msi",
    "mmr",
    "egfr",
    "alk",
    "ros1",
    "kras",
    "nras",
    "braf",
    "brca",
    "biologie moleculaire",
    # Invasion pleurale
    "invasion pleurale",
    "invasion du muscle",
    # Extension tumorale
    "extension extra",
    "rupture capsulaire",
    "invasion du muscle",
    "invasion de la graisse",
    "invasion de la veine",
    "invasion du rete",
    "invasion du systeme collecteur",
    # Score de regression tumorale
    "score de regression",
    "trg",
    # Tumour budding
    "tumour budding",
    # Composante in situ
    "composante in situ",
    # Effraction capsulaire
    "effraction capsulaire",
    # Microsatellitose
    "microsatellitose",
]

# ---------------------------------------------------------------------------
# Champs specifiques aux PIECES OPERATOIRES (pas aux biopsies)
# ---------------------------------------------------------------------------

_CHAMPS_PIECE_OPERATOIRE_SEUL: list[str] = [
    "ptnm",
    "tnm",
    "staging",
    "stade",
    "marge",
    "limites d'exerese",
    "limites chirurgicales",
    "limite",
    "recoupe",
    "crm",
    "circonferentielle",
    "ganglion",
    "curage",
    "ganglionnaire",
    "sentinelle",
    "mesorectum",
    "qualite du mesorectum",
    "score de regression",
    "trg",
    "effraction capsulaire",
    "extension extra",
    "rupture capsulaire",
    "invasion du muscle",
    "invasion de la graisse",
    "microsatellitose",
]

# ---------------------------------------------------------------------------
# Champs non pertinents pour les lesions pre-cancereuses / in situ
# (AIN, dysplasie de haut grade, HSIL, CIS, DCIS, LCIS)
# ---------------------------------------------------------------------------

_CHAMPS_EXCLUS_PRE_CANCEREUX: list[str] = [
    "ptnm",
    "tnm",
    "staging",
    "stade",
    "marge",
    "limites d'exerese",
    "ganglion",
    "curage",
    "ganglionnaire",
    "embole",
    "invasion vasculaire",
    "invasion lympho",
    "engainement",
    "perinerveux",
    "perineural",
    "taille tumorale",
    "taille de la tumeur",
    "invasion pleurale",
    "extension extra",
    "effraction capsulaire",
    "score de regression",
    "microsatellitose",
    "tumour budding",
    "composante in situ",
]


# ---------------------------------------------------------------------------
# Fonctions utilitaires
# ---------------------------------------------------------------------------

def _normaliser_texte(texte: str) -> str:
    """Normalise le texte pour la recherche de mots-cles (minuscules, sans accents basiques)."""
    resultat: str = texte.lower()
    # Remplacement basique des accents les plus courants
    remplacements: dict[str, str] = {
        "é": "e",
        "è": "e",
        "ê": "e",
        "ë": "e",
        "à": "a",
        "â": "a",
        "ä": "a",
        "ù": "u",
        "û": "u",
        "ü": "u",
        "ô": "o",
        "ö": "o",
        "î": "i",
        "ï": "i",
        "ç": "c",
    }
    for accent, remplacement in remplacements.items():
        resultat = resultat.replace(accent, remplacement)
    return resultat


def _champ_present_dans_rapport(
    champ: ChampObligatoire, rapport_normalise: str
) -> bool:
    """Verifie si un champ obligatoire est present dans le rapport.

    Un champ est considere present si AU MOINS UN de ses mots-cles de
    detection apparait dans le texte normalise du rapport.
    """
    for mot_cle in champ.mots_cles_detection:
        mot_cle_normalise: str = _normaliser_texte(mot_cle)
        if mot_cle_normalise in rapport_normalise:
            return True
    return False


def _section_presente(section: str, rapport_normalise: str) -> bool:
    """Verifie si une section existe dans le rapport."""
    noms_section: list[str] = _SECTIONS_MAPPING.get(section, [section])
    for nom in noms_section:
        if _normaliser_texte(nom) in rapport_normalise:
            return True
    return False


# ---------------------------------------------------------------------------
# Detection du contexte tumoral
# ---------------------------------------------------------------------------

def _masquer_negations(rapport_normalise: str) -> str:
    """Remplace les phrases de negation par des espaces dans le texte.

    Strategie en deux passes :
    1. Masquer les phrases negatives connues (remplacement direct).
    2. Masquer toute portion de phrase commencant par un marqueur de negation
       (pas de, absence de, sans, ni de, il n'est pas observe de, etc.)
       jusqu'au point ou a la fin de la ligne. Cela couvre les cas comme
       'il n est pas observe de granulome ni de proliferation tumorale.'
    """
    resultat: str = rapport_normalise

    # Passe 1 : phrases connues
    for phrase in _PHRASES_NEGATION:
        phrase_norm: str = _normaliser_texte(phrase)
        resultat = resultat.replace(phrase_norm, " " * len(phrase_norm))

    # Passe 2 : masquer depuis un marqueur negatif jusqu'au prochain point/fin de ligne
    neg_markers: list[str] = [
        r"il n.{0,3}est pas observe de\b",
        r"il n.{0,3}est pas vu de\b",
        r"il n.{0,3}y a pas de\b",
        r"\babsence de\b",
        r"\bpas de\b",
        r"\bsans\b",
        r"\bni de\b",
        r"\bindemne de\b",
        r"\bindemnes de\b",
    ]
    combined_pattern: str = "|".join(neg_markers)
    for match in re.finditer(combined_pattern, resultat):
        start: int = match.start()
        # Trouver la fin : prochain point, prochain retour a la ligne, ou fin du texte
        end: int = len(resultat)
        for sep in [".", "\n"]:
            pos: int = resultat.find(sep, match.end())
            if pos != -1 and pos < end:
                end = pos
        resultat = resultat[:start] + " " * (end - start) + resultat[end:]

    return resultat


def _est_contexte_tumoral(rapport_normalise: str) -> bool:
    """Determine si le rapport concerne une tumeur.

    La detection se fait en deux etapes :

    1. **Mots-cles non ambigus** (carcinome, adenocarcinome, melanome, etc.) :
       leur simple presence suffit a conclure a un contexte tumoral.

    2. **Mots-cles ambigus** (tumeur, malin, infiltrant, etc.) : ils ne
       comptent que s'ils apparaissent au moins une fois EN DEHORS d'une
       phrase de negation ("pas de ...", "absence de ...", "sans ...").

    Retourne True si le rapport decrit une tumeur, False sinon.
    """
    # Etape 1 : mots-cles non ambigus — presence directe
    for mot_cle in _MOTS_CLES_TUMEUR:
        if _normaliser_texte(mot_cle) in rapport_normalise:
            return True

    # Etape 2 : mots-cles ambigus — presence hors phrases de negation
    texte_sans_negations: str = _masquer_negations(rapport_normalise)
    for mot_cle in _MOTS_CLES_TUMEUR_AMBIGUS:
        if _normaliser_texte(mot_cle) in texte_sans_negations:
            return True

    return False


def _est_biopsie(rapport_normalise: str) -> bool:
    """Detecte si le rapport concerne une biopsie (pas une piece operatoire)."""
    mots_biopsie: list[str] = [
        "biopsie", "biopsique", "carotte", "fragment biopsique",
        "punch", "microbiopsie", "macrobiopsie",
    ]
    mots_piece: list[str] = [
        "piece operatoire", "tumorectomie", "mastectomie", "colectomie",
        "gastrectomie", "nephrectomie", "prostatectomie", "lobectomie",
        "pneumonectomie", "thyroidectomie", "hysterectomie", "exerese",
        "amputation", "resection",
    ]
    has_biopsie: bool = any(m in rapport_normalise for m in mots_biopsie)
    has_piece: bool = any(m in rapport_normalise for m in mots_piece)
    # Si les deux sont presents, c'est probablement une piece
    if has_piece:
        return False
    # Si ni biopsie ni piece n'est detecte, retourner False (indetermine)
    return has_biopsie


def _est_pre_cancereux(rapport_normalise: str) -> bool:
    """Detecte si le diagnostic est pre-cancereux / in situ (pas infiltrant)."""
    mots_pre_cancereux: list[str] = [
        "ain1", "ain2", "ain3",
        "hsil", "lsil",
        "dysplasie de haut grade", "dysplasie de bas grade",
        "neoplasie intraepitheliale",
        "in situ",
        "carcinome in situ",
        "dcis", "lcis",
        "hyperplasie", "metaplasie",
    ]
    mots_infiltrant: list[str] = [
        "infiltrant", "infiltrante", "invasif", "invasive",
        "carcinome infiltrant", "adenocarcinome infiltrant",
    ]
    texte_sans_negations: str = _masquer_negations(rapport_normalise)
    has_pre: bool = any(m in rapport_normalise for m in mots_pre_cancereux)
    has_infiltrant: bool = any(m in texte_sans_negations for m in mots_infiltrant)
    # "absence de carcinome infiltrant" ne compte PAS comme infiltrant
    return has_pre and not has_infiltrant


def _est_champ_piece_operatoire_seul(nom_champ: str) -> bool:
    """Verifie si un champ ne s'applique qu'aux pieces operatoires."""
    nom_normalise: str = _normaliser_texte(nom_champ)
    for exclu in _CHAMPS_PIECE_OPERATOIRE_SEUL:
        if exclu in nom_normalise:
            return True
    return False


def _est_champ_pre_cancereux_exclu(nom_champ: str) -> bool:
    """Verifie si un champ est non pertinent pour les lesions pre-cancereuses."""
    nom_normalise: str = _normaliser_texte(nom_champ)
    for exclu in _CHAMPS_EXCLUS_PRE_CANCEREUX:
        if exclu in nom_normalise:
            return True
    return False


def _est_champ_tumeur_seul(nom_champ: str) -> bool:
    """Verifie si un champ est specifique au contexte tumoral.

    Retourne True si le nom du champ (normalise) correspond a l'un des
    champs de la liste d'exclusion pour rapports non-tumoraux.
    """
    nom_normalise: str = _normaliser_texte(nom_champ)
    for exclu in _CHAMPS_EXCLUS_NON_TUMEUR:
        if exclu in nom_normalise:
            return True
    return False


# ---------------------------------------------------------------------------
# Extraction des marqueurs [A COMPLETER]
# ---------------------------------------------------------------------------

def _deviner_section_depuis_contexte(
    rapport: str, position: int
) -> str:
    """Devine la section d'un marqueur [A COMPLETER] en analysant le contexte.

    Remonte dans le texte depuis la position du marqueur pour trouver
    le dernier titre de section.
    """
    texte_avant: str = _normaliser_texte(rapport[:position])

    # Chercher la derniere section mentionnee avant le marqueur
    derniere_section: str = "non_determine"
    derniere_position: int = -1

    for section, noms in _SECTIONS_MAPPING.items():
        for nom in noms:
            nom_norm: str = _normaliser_texte(nom)
            pos: int = texte_avant.rfind(nom_norm)
            if pos > derniere_position:
                derniere_position = pos
                derniere_section = section

    return derniere_section


def extraire_marqueurs_a_completer(rapport: str) -> list[DonneeManquante]:
    """Extrait les marqueurs [A COMPLETER: xxx] du rapport.

    Parcourt le rapport a la recherche de tous les patterns
    [A COMPLETER: description] et les convertit en objets DonneeManquante.

    C'est la source PRIMAIRE de detection : le LLM connait le contexte
    clinique et n'insere ces marqueurs que pour les champs veritablement
    pertinents.

    Args:
        rapport: Le compte-rendu formate en Markdown.

    Returns:
        Liste de DonneeManquante extraites des marqueurs.
    """
    resultats: list[DonneeManquante] = []
    noms_vus: set[str] = set()

    for match in _PATTERN_A_COMPLETER.finditer(rapport):
        description_brute: str = match.group(1).strip()

        # Eviter les doublons si le meme marqueur apparait plusieurs fois
        cle: str = _normaliser_texte(description_brute)
        if cle in noms_vus:
            continue
        noms_vus.add(cle)

        # Deviner la section depuis le contexte
        section: str = _deviner_section_depuis_contexte(rapport, match.start())

        resultats.append(
            DonneeManquante(
                champ=description_brute,
                description=f"Champ manquant identifie par le systeme : {description_brute}",
                section=section,
                obligatoire=True,
            )
        )

    return resultats


# ---------------------------------------------------------------------------
# Fonction principale
# ---------------------------------------------------------------------------

def detecter_donnees_manquantes(
    rapport: str, organe: str
) -> list[DonneeManquante]:
    """Validations structurelles du CR — complement des alertes de Claude.

    Claude genere deja les alertes pertinentes via son JSON de sortie.
    Ce module ajoute uniquement des validations structurelles que Claude
    peut oublier de lever :

    1. Marqueurs ``[A COMPLETER: xxx]`` que Claude a inseres dans le CR
       (extraction texte -> liste DonneeManquante).
    2. Validation multi-specimens : chaque specimen numerote doit avoir
       sa Macroscopie et sa Microscopie titrees.

    Les parametres ``organe`` et le contexte diagnostique ne sont plus
    utilises — Claude gere tout le raisonnement par organe lui-meme.

    Args:
        rapport: Le compte-rendu formate en Markdown.
        organe: Identifiant de l'organe deduit par Claude (non utilise ici).

    Returns:
        Liste de DonneeManquante (marqueurs + multi-specimens).
    """
    del organe  # signature conservee pour compatibilite des appelants

    manquantes: list[DonneeManquante] = []
    champs_deja_signales: set[str] = set()

    # ----- Passe A : marqueurs [A COMPLETER: xxx] inseres dans le CR -----
    for marqueur in extraire_marqueurs_a_completer(rapport):
        nom_normalise: str = _normaliser_texte(marqueur.champ)
        if nom_normalise not in champs_deja_signales:
            manquantes.append(marqueur)
            champs_deja_signales.add(nom_normalise)

    # ----- Passe B : validation structurelle multi-specimens -----
    manquantes.extend(_detecter_sections_multispecimens_manquantes(rapport))

    return manquantes


# Pattern : sous-sections numerotees type "**__1) ...__**" ou "1) ..." ou "1°/ ..."
_PATTERN_SOUS_SECTION: re.Pattern[str] = re.compile(
    r"(?:^|\n)\s*(?:\*\*__)?(\d+)\s*[)°][/°]?\s*([^\n:]+?)\s*:?\s*(?:__\*\*)?\s*$",
    re.MULTILINE,
)


def _detecter_sections_multispecimens_manquantes(
    rapport: str,
) -> list[DonneeManquante]:
    """Si le rapport contient plusieurs specimens numerotes, verifie que
    CHAQUE specimen possede une Macroscopie et une Microscopie titrees.

    Corrige le bug multi-specimens (ex: pelviglossectomie + curages +
    recoupes) ou le systeme marquait le CR comme complet alors qu'il
    manquait des sections.
    """
    matches: list[re.Match[str]] = list(_PATTERN_SOUS_SECTION.finditer(rapport))
    if len(matches) < 2:
        return []

    manquantes: list[DonneeManquante] = []

    for idx, match in enumerate(matches):
        numero: str = match.group(1)
        titre_specimen: str = match.group(2).strip()
        debut: int = match.end()
        fin: int = matches[idx + 1].start() if idx + 1 < len(matches) else len(rapport)
        bloc: str = rapport[debut:fin]
        bloc_normalise: str = _normaliser_texte(bloc)

        if not _section_presente("macroscopie", bloc_normalise):
            manquantes.append(
                DonneeManquante(
                    champ=f"Macroscopie du specimen {numero} ({titre_specimen})",
                    description=(
                        "Chaque specimen numerote doit avoir sa propre "
                        "section Macroscopie."
                    ),
                    section="macroscopie",
                    obligatoire=True,
                )
            )

        if not _section_presente("microscopie", bloc_normalise):
            manquantes.append(
                DonneeManquante(
                    champ=f"Microscopie du specimen {numero} ({titre_specimen})",
                    description=(
                        "Chaque specimen numerote doit avoir sa propre "
                        "section Microscopie avec une description morphologique."
                    ),
                    section="microscopie",
                    obligatoire=True,
                )
            )

    return manquantes


def calculer_score_completude(
    rapport: str, organe: str
) -> dict[str, int | float]:
    """Calcule le score de completude INCa du rapport.

    Utilise la meme logique que detecter_donnees_manquantes (via
    specimen_type.champ_applicable) pour la coherence des resultats.

    Retourne le nombre de champs obligatoires presents sur le total,
    et le pourcentage de completude.
    """
    rapport_normalise: str = _normaliser_texte(rapport)
    specimen: SpecimenType = detecter_specimen_type(rapport)
    contexte: DiagnosticContext = detecter_diagnostic_context(rapport)

    champs: list[ChampObligatoire] = get_champs_obligatoires(organe)
    total: int = 0
    presents: int = 0

    for champ in champs:
        if not champ.obligatoire:
            continue

        if not champ_applicable(champ.nom, specimen, contexte):
            continue

        total += 1
        if _champ_present_dans_rapport(champ, rapport_normalise):
            presents += 1

    pourcentage: float = (presents / total * 100) if total > 0 else 100.0

    return {
        "score": presents,
        "total_champs": total,
        "champs_presents": presents,
        "pourcentage": round(pourcentage, 1),
    }
