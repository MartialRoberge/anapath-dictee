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
from text_utils import normaliser as _normaliser_texte
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

# Termes trop generiques pour constituer a eux seuls un champ affichable
# (un marqueur "[A COMPLETER: grade]" ou "[A COMPLETER: resultat]" est inexploitable).
_MARQUEURS_GENERIQUES: frozenset[str] = frozenset({
    "grade", "resultat", "resultats", "valeur", "valeurs", "score", "statut",
    "type", "preciser", "precisez", "a", "completer", "le", "la", "les", "de",
    "du", "des", "un", "une", "si", "realise", "realisee", "en", "et", "ou",
    "detail", "details", "information", "donnee", "donnees",
    "pourcentage", "pourcentages", "intensite", "positivite", "proportion",
})

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


def _champ_present_dans_rapport(
    champ: ChampObligatoire, rapport_normalise: str
) -> bool:
    """Verifie si un champ obligatoire est present dans le rapport.

    Un champ est considere present si AU MOINS UN de ses mots-cles de
    detection apparait dans le texte normalise. Les mots-cles COURTS (<=3
    caracteres, ex "RE", "RP", "MSI") sont recherches a limites de mots pour
    eviter les faux positifs (ex "re" contenu dans "sereuse") qui faisaient
    croire un champ present a tort et le retiraient du rappel.
    """
    for mot_cle in champ.mots_cles_detection:
        mot_cle_normalise: str = _normaliser_texte(mot_cle).strip()
        if not mot_cle_normalise:
            continue
        if len(mot_cle_normalise) <= 3:
            if re.search(rf"\b{re.escape(mot_cle_normalise)}\b", rapport_normalise):
                return True
        elif mot_cle_normalise in rapport_normalise:
            return True
    return False


def _section_presente(section: str, rapport_normalise: str) -> bool:
    """Verifie si une section existe dans le rapport."""
    noms_section: list[str] = _SECTIONS_MAPPING.get(section, [section])
    for nom in noms_section:
        if _normaliser_texte(nom) in rapport_normalise:
            return True
    return False


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


# Formulations rendant un champ RECOMMANDE (optionnel) plutot qu'obligatoire.
_PHRASES_CONDITIONNELLES: tuple[str, ...] = (
    "si realise", "si applicable", "si disponible", "le cas echeant",
    "si connu", "eventuel", "si present", "si effectue", "si indique",
)


def _marqueur_nom_exploitable(description_brute: str) -> bool:
    """Un marqueur [A COMPLETER: ...] designe-t-il un vrai champ nomme ?

    Ecarte (le rappel deterministe fournit le champ nomme a la place) :
    - les marqueurs GENERIQUES NUS ("grade", "resultat", "valeur"...) ;
    - les fragments d'INSTRUCTION ("preciser le pourcentage", "precisez 0/1+...").
    """
    coeur = _normaliser_texte(description_brute.split("(")[0])
    tokens_utiles = [t for t in coeur.split() if t not in _MARQUEURS_GENERIQUES]
    if not tokens_utiles:
        return False
    if coeur.startswith(("preciser", "precisez", "precise ")):
        return False
    return True


def _est_champ_conditionnel(cle_normalisee: str) -> bool:
    """Le champ est-il optionnel ('si realise', 'si applicable'...) ?"""
    return any(phrase in cle_normalisee for phrase in _PHRASES_CONDITIONNELLES)


def extraire_marqueurs_a_completer(rapport: str) -> list[DonneeManquante]:
    """Extrait les marqueurs [A COMPLETER: xxx] du rapport en DonneeManquante.

    Source PRIMAIRE de detection : le LLM connait le contexte clinique et n'insere
    ces marqueurs que pour les champs pertinents. On deduplique, on ecarte les
    marqueurs non exploitables, on devine la section et le caractere obligatoire.
    """
    resultats: list[DonneeManquante] = []
    noms_vus: set[str] = set()

    for match in _PATTERN_A_COMPLETER.finditer(rapport):
        description_brute: str = match.group(1).strip()

        cle: str = _normaliser_texte(description_brute)
        if cle in noms_vus:  # meme marqueur repete
            continue
        noms_vus.add(cle)

        if not _marqueur_nom_exploitable(description_brute):
            continue

        section: str = _deviner_section_depuis_contexte(rapport, match.start())
        est_conditionnel: bool = _est_champ_conditionnel(cle)

        resultats.append(
            DonneeManquante(
                champ=description_brute,
                description=f"Champ manquant identifie par le systeme : {description_brute}",
                section=section,
                obligatoire=not est_conditionnel,
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


def detecter_champs_obligatoires_manquants(
    rapport: str, organes: list[str]
) -> list[DonneeManquante]:
    """Rappel DETERMINISTE des champs obligatoires INCa absents du CR.

    Complement du LLM (probabiliste) : pour CHAQUE organe detecte, parcourt les
    champs obligatoires du referentiel, ne garde que ceux APPLICABLES au type de
    prelevement et a la nature de la lesion (via ``champ_applicable`` — donc pas
    de pTNM sur biopsie, pas de grade sur benin...), et signale ceux ABSENTS du
    CR. Garantit le rappel des champs pronostiques reglementaires meme si le LLM
    les a oublies, sans introduire de faux positif (double filtrage aval).
    """
    rapport_normalise: str = _normaliser_texte(rapport)
    specimen: SpecimenType = detecter_specimen_type(rapport)
    contexte: DiagnosticContext = detecter_diagnostic_context(rapport)

    manquants: list[DonneeManquante] = []
    vus: set[str] = set()
    for organe in organes or []:
        for champ in get_champs_obligatoires(organe):
            if not champ.obligatoire:
                continue
            if not champ_applicable(champ.nom, specimen, contexte):
                continue
            if _champ_present_dans_rapport(champ, rapport_normalise):
                continue
            cle = _normaliser_texte(champ.nom)
            if cle in vus:
                continue
            vus.add(cle)
            manquants.append(
                DonneeManquante(
                    champ=champ.nom,
                    description=champ.exemple_formulation or champ.description,
                    section=champ.section,
                    obligatoire=True,
                )
            )
    return manquants
