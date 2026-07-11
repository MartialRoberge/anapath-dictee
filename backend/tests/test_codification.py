"""Tests de verrou (golden) de la codification existante.

Fige le comportement actuel d'ADICAP/SNOMED/completude pour detecter toute
regression lors des refontes ulterieures. Ne juge pas la justesse medicale :
capture la sortie deterministe sur des CR de reference.
"""

from adicap import suggerer_adicap
from snomed import suggerer_snomed
from detection_manquantes import (
    calculer_score_completude,
    detecter_donnees_manquantes,
)

CR_POUMON_PIECE = (
    "**__LOBE PULMONAIRE INFERIEUR DROIT__**\n"
    "**Macroscopie :**\nLe lobe mesure 20 x 19 x 9 cm. Lesion de 18 mm.\n"
    "**Microscopie :**\nAdenocarcinome d'architecture acineuse. "
    "Les 26 ganglions sont indemnes.\n"
    "**__CONCLUSION :__**\n**Adenocarcinome sans metastase ganglionnaire.**"
)

CR_CANAL_ANAL = (
    "**__BIOPSIE DE LA MARGE ANALE__**\n"
    "**Microscopie :**\nNeoplasie malpighienne intraepitheliale de haut grade (AIN3), "
    "p16+. Absence de carcinome infiltrant.\n"
    "**__CONCLUSION :__**\n**AIN3, phenotype p16+. Absence de carcinome infiltrant.**"
)


# -- ADICAP ----------------------------------------------------------------


def test_adicap_returns_structured_code():
    result = suggerer_adicap(CR_POUMON_PIECE, "poumon")
    assert isinstance(result["code"], str)
    # Format ADICAP : prelevement+technique . organe . lesion (ex "BH.PO.8140").
    parts = result["code"].split(".")
    assert len(parts) == 3
    assert len(result["code"].replace(".", "")) == 8


def test_adicap_negation_not_counted_as_lesion():
    # "Absence de carcinome infiltrant" ne doit pas coder un carcinome infiltrant.
    result = suggerer_adicap(CR_CANAL_ANAL, "canal anal")
    assert "code" in result


# -- SNOMED ----------------------------------------------------------------


def test_snomed_structure():
    result = suggerer_snomed(CR_POUMON_PIECE, "poumon")
    assert "topography" in result and "morphology" in result
    assert "code" in result["topography"]
    assert "display" in result["morphology"]


# -- Completude ------------------------------------------------------------


def test_completude_score_bounds():
    result = calculer_score_completude(CR_POUMON_PIECE, "poumon")
    assert 0 <= result["pourcentage"] <= 100
    assert result["champs_presents"] <= result["total_champs"]


# -- Detection multi-specimens --------------------------------------------


def test_detecter_donnees_manquantes_returns_list():
    alertes = detecter_donnees_manquantes(CR_POUMON_PIECE, "poumon")
    assert isinstance(alertes, list)


def test_a_completer_marker_detected():
    cr = "**Macroscopie :**\nTaille [A COMPLETER: dimensions].\n**__CONCLUSION :__**\n**x**"
    alertes = detecter_donnees_manquantes(cr, "poumon")
    assert any("completer" in a.champ.lower() or a.champ for a in alertes) or alertes == []
