"""Le menu deroulant et la phrase declenchante doivent ATTEINDRE L'ECRAN.

TROIS VERROUS LES DETRUISAIENT, tous en aval de leur lecture. Le code des
selecteurs existait cote interface et n'etait jamais atteint ; le panneau
« Pourquoi » retombait sur une phrase passe-partout. Le proprietaire a demande
des menus deroulants a plusieurs reprises, et ils ne pouvaient pas apparaitre.

1. `build_validated_report` rebatissait chaque alerte avec trois champs, en
   jetant `declencheur`, `raison` et `options`.
2. `merge_donnees_manquantes` ecartait l'alerte du modele des qu'un marqueur
   deterministe portait un nom proche — or l'alerte du modele est la SEULE a
   porter les options et le declencheur.
3. `filter_present_alertes` supprimait l'entree quand le nom du champ figurait
   dans la phrase entourant le marqueur : « Le grade de dysplasie est
   [A COMPLETER: grade de dysplasie] » ne laissait plus rien du tout.

Ces tests tiennent les trois.
"""

from __future__ import annotations

from models import DonneeManquante
from reports.engine import GeneratedReport
from reports.guardrails import filter_present_alertes
from reports.panel import build_panel, merge_donnees_manquantes
from specimen_type import SpecimenType

ALERTE = DonneeManquante(
    champ="grade de dysplasie",
    description="Précisez le grade.",
    section="conclusion",
    declencheur="adenome tubuleux du colon sigmoide",
    raison="Un adenome se grade toujours.",
    options=["bas grade", "haut grade"],
)


def _rapport(cr: str) -> GeneratedReport:
    return GeneratedReport(
        cr=cr,
        organe="colon",
        organes_detectes=["colon"],
        type_prelevement=SpecimenType.BIOPSIE,
        alertes=[ALERTE],
        warnings=[],
        provider="test",
        model="test",
    )


def _grade(panel: list[DonneeManquante]) -> DonneeManquante | None:
    return next((d for d in panel if "grade de dys" in d.champ.lower()), None)


def test_le_menu_et_le_declencheur_traversent_tout_le_chemin():
    """LE TEST DE BOUT EN BOUT. Il tombe si l'un des trois verrous revient."""
    cr = (
        "**Conclusion :**\n"
        "Adenome tubuleux du colon sigmoide, [A COMPLETER: grade de dysplasie].\n"
    )
    trouve = _grade(build_panel(_rapport(cr)))
    assert trouve is not None, "le trou n'a plus aucun complement"
    assert trouve.options == ["bas grade", "haut grade"], (
        "le menu deroulant n'atteint pas l'ecran"
    )
    assert trouve.declencheur == "adenome tubuleux du colon sigmoide"
    assert trouve.raison == "Un adenome se grade toujours."


def test_le_nom_du_champ_dans_la_phrase_ne_supprime_plus_l_entree():
    """UN MARQUEUR OUVERT EST LA PREUVE QUE LE CHAMP N'EST PAS REMPLI. Le
    filtre anti-faux-positif le prenait pour un champ deja renseigne."""
    cr = "Le grade de dysplasie est [A COMPLETER: grade de dysplasie].\n"
    gardees, retirees = filter_present_alertes([ALERTE], cr)
    assert gardees == [ALERTE]
    assert retirees == 0


def test_un_champ_reellement_rempli_reste_ecarte():
    """Le garde-fou anti-faux-positif doit continuer de marcher : sans marqueur
    ouvert, un champ deja renseigne n'est pas a reclamer."""
    cr = "Adenome tubuleux en dysplasie de bas grade.\n"
    _, retirees = filter_present_alertes([ALERTE], cr)
    assert retirees == 1


def test_la_fusion_enrichit_le_marqueur_au_lieu_de_jeter_l_alerte():
    """Le marqueur garde son NOM — l'interface rapproche par ce nom — et
    recupere ce qu'il n'a pas : les options, le declencheur, la vraie raison."""
    deterministe = DonneeManquante(
        champ="grade de dysplasie",
        description="Champ manquant identifie par le systeme.",
        section="conclusion",
        raison="Donnee du compte rendu minimal pour ce type de prelevement.",
    )
    [fusionne] = merge_donnees_manquantes([deterministe], [ALERTE])
    assert fusionne.champ == "grade de dysplasie"
    assert fusionne.options == ["bas grade", "haut grade"]
    assert fusionne.declencheur == "adenome tubuleux du colon sigmoide"
    assert fusionne.raison == "Un adenome se grade toujours.", (
        "la phrase passe-partout du marqueur ecrase la raison du modele"
    )
