"""Construction du panneau "a completer" presente au pathologiste.

Logique METIER (pas HTTP) : a partir d'un CR genere, assemble les champs a
completer en fusionnant trois sources, puis en appliquant deux gardes de securite.
Extrait de main.py pour que le module d'entree API reste du simple cablage.

Pipeline (``build_panel``) :
1. marqueurs [A COMPLETER] inseres par le LLM (deterministe) ;
2. RAPPEL deterministe des champs obligatoires INCa applicables absents ;
3. recommandations du LLM (probabilistes) ;
   -> fusion dedupliquee, puis filtre de securite (hors-contexte organe/prelevement/
   nature de lesion) et anti-faux-positif (deja present dans le CR) ;
4. systemes de reporting standardises (cytologie/medical), ajoutes en dernier.
"""

from __future__ import annotations

from models import DonneeManquante
from detection_manquantes import (
    detecter_donnees_manquantes,
    detecter_champs_obligatoires_manquants,
)
from specimen_type import SpecimenType, detecter_diagnostic_context
from text_utils import cle_alphanum, normaliser
from reports.engine import GeneratedReport
from reports.guardrails import filter_alertes, filter_present_alertes
from reports.reporting_systems import suggest_reporting_fields

# Sarcomes a cellules rondes / pediatriques : hauts grades par definition, cotes
# par d'autres systemes (IRS/COG/SIOP), pas par le FNCLCC -> on retire ce champ.
_SARCOMES_NON_FNCLCC: tuple[str, ...] = (
    "rhabdomyosarcome", "ewing", "neuroblastome", "embryonnaire",
    "desmoplastique a petites cellules", "pnet",
)


def merge_donnees_manquantes(
    deterministes: list[DonneeManquante], recommandees: list[DonneeManquante]
) -> list[DonneeManquante]:
    """Fusionne les champs deterministes (marqueurs [A COMPLETER], obligatoires) et
    les recommandations LLM (probabilistes) en dedupliquant : un champ deja couvert
    par un marqueur deterministe n'est pas re-liste."""
    resultat: list[DonneeManquante] = list(deterministes)
    vus: list[str] = [cle_alphanum(d.champ) for d in deterministes]
    for reco in recommandees:
        cle = cle_alphanum(reco.champ)
        if not cle:
            continue
        # Dedoublonnage par inclusion : "ptnm" et "ptnmtnm8esein" sont le meme champ.
        if any(cle in v or v in cle for v in vus):
            continue
        resultat.append(reco)
        vus.append(cle)
    return resultat


def safety_filter_panel(
    donnees: list[DonneeManquante], result: GeneratedReport
) -> list[DonneeManquante]:
    """Filtre de securite du panneau FINAL (marqueurs deterministes inclus).

    Garantit qu'aucun champ hors-contexte organe / prelevement / nature de lesion
    n'apparait, quelle que soit sa source (LLM ou marqueur [A COMPLETER]) : un champ
    tumoral ne peut pas apparaitre sur une lesion benigne.
    """
    try:
        specimen = SpecimenType(result.type_prelevement)
    except ValueError:
        specimen = SpecimenType.INDETERMINE
    contexte = detecter_diagnostic_context(result.cr).value
    filtres, _ = filter_alertes(donnees, result.organes_detectes, specimen, contexte)
    return filtres


def polish_panel(panel: list[DonneeManquante], cr: str) -> list[DonneeManquante]:
    """Finition du panneau : retire les champs inadaptes au sous-site — le
    'mesorectum' (concept RECTAL) n'a pas de sens sur un colon/sigmoide, le FNCLCC
    n'a pas de sens sur un sarcome pediatrique a cellules rondes."""
    low_cr = normaliser(cr)
    has_rectum = "rectum" in low_cr or "rectal" in low_cr
    sarcome_non_fnclcc = any(w in low_cr for w in _SARCOMES_NON_FNCLCC)

    def _garder(d: DonneeManquante) -> bool:
        n = normaliser(d.champ)
        if "mesorect" in n and not has_rectum:
            return False
        if "fnclcc" in n and sarcome_non_fnclcc:
            return False
        return True

    return [d for d in panel if _garder(d)]


def build_panel(result: GeneratedReport) -> list[DonneeManquante]:
    """Construit le panneau "a completer" (meme pipeline pour /format et /iterate)."""
    marqueurs = detecter_donnees_manquantes(result.cr, result.organe)
    obligatoires = detecter_champs_obligatoires_manquants(
        result.cr, result.organes_detectes
    )
    panel = merge_donnees_manquantes(marqueurs + obligatoires, result.alertes)
    panel = safety_filter_panel(panel, result)
    panel, _ = filter_present_alertes(panel, result.cr)
    panel = polish_panel(panel, result.cr)
    # Systemes de reporting ajoutes APRES l'anti-faux-positif : le module a son
    # propre controle de presence precis (categorie/score reellement rempli),
    # sinon ses mots-cles declencheurs presents dans le CR le supprimeraient a tort.
    reporting = [
        DonneeManquante(
            champ=champ,
            description="Systeme de reporting standardise applicable — a renseigner "
            "par le pathologiste (jamais cote automatiquement).",
            section="reporting",
        )
        for champ in suggest_reporting_fields(result.cr)
    ]
    return merge_donnees_manquantes(panel, reporting)
