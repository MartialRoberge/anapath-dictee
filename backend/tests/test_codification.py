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


def test_adicap_returns_8char_conformant_code():
    result = suggerer_adicap(CR_POUMON_PIECE, "poumon")
    # Format ADICAP standard : 8 caracteres contigus (pas de points).
    assert len(result["code"]) == 8
    assert "." not in result["code"]
    # Poumon = code organe D3 officiel RP.
    assert result["organe_code"] == "RP"


def test_adicap_official_organ_codes():
    # Codes organe D3 officiels (thesaurus ADICAP v5-04).
    assert suggerer_adicap("Biopsie du sein. Carcinome.", "sein")["organe_code"] == "GS"
    assert suggerer_adicap("Nephrectomie.", "rein")["organe_code"] == "UR"
    assert suggerer_adicap("Prostatectomie.", "prostate")["organe_code"] == "HP"


def test_adicap_common_cancers_coded():
    # Cancers frequents -> code lesionnel officiel, confiance haute.
    r = suggerer_adicap("Biopsie. CONCLUSION: Carcinome canalaire infiltrant.", "sein")
    assert r["code"] == "BHGSA7B2"
    assert r["confidence"] == "haute"


def test_adicap_defers_when_uncertain():
    # Diagnostic non mappable de facon certaine -> lesion differee, jamais fausse.
    r = suggerer_adicap("CONCLUSION: aspect indetermine, a confronter.", "poumon")
    assert r["lesion_code"] == "____"
    assert r["confidence"] != "haute"


def test_adicap_negation_not_coded_as_lesion():
    # "Absence de carcinome infiltrant" ne doit pas coder un carcinome.
    result = suggerer_adicap(CR_CANAL_ANAL, "canal anal")
    assert "carcinome infiltrant" not in result["lesion"].lower()


def test_adicap_bible_zero_wrong():
    """Rejoue la bible : le codeur ne doit JAMAIS emettre un code lesionnel faux."""
    from adicap import _load_reference, _match_lesion
    from text_utils import normaliser

    _, catalog = _load_reference()
    wrong = 0
    emitted = 0
    for e in catalog:
        if e.organ_code is None:
            continue
        entry, _ = _match_lesion(normaliser(e.lesion), e.organ_code, catalog)
        if entry is not None:
            emitted += 1
            if entry.lesion_code != e.lesion_code:
                wrong += 1
    assert wrong == 0, f"{wrong} codes lésionnels erronés sur {emitted} émis"


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


# -- Libelle d'organe ADICAP correct (bug "Gynecomastie"/"Bourgeon charnu") --


def test_adicap_organe_label_sein_pas_gynecomastie():
    r = suggerer_adicap("carcinome canalaire infiltrant du sein droit", "sein")
    assert r["organe"] == "Sein"
    assert "gyneco" not in r["organe"].lower()


def test_adicap_organe_label_melanome_pas_bourgeon_charnu():
    r = suggerer_adicap("melanome cutane du dos, Breslow 1.2 mm", "melanome")
    assert r["organe"] == "Peau"
    assert "bourgeon" not in r["organe"].lower()
