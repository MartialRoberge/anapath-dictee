"""Systemes de reporting standardises : propose la categorie/score attendu
(cytologie, pathologie medicale) sans jamais coter a la place, et seulement
quand c'est applicable et non deja renseigne."""

from reports.reporting_systems import suggest_reporting_fields


def test_epanchement_propose_systeme_sereux():
    champs = suggest_reporting_fields(
        "Cytologie d'un liquide pleural, cellularite mesotheliale reactionnelle."
    )
    assert any("epanchements sereux" in c for c in champs)


def test_greffon_renal_propose_banff():
    champs = suggest_reporting_fields(
        "Biopsie du greffon renal, tubulite focale, pas de C4d realise."
    )
    assert any("Banff" in c for c in champs)


def test_mest_c_propose_sur_iga():
    # Apostrophe courbe du CR ("d'IgA") ne doit pas casser la detection.
    champs = suggest_reporting_fields(
        "Nephropathie a depots mesangiaux d’IgA, hypercellularite mesangiale."
    )
    assert any("MEST-C" in c for c in champs)


def test_banff_propose_sur_slot_vide():
    # Le nom du systeme sur un slot vide ("selon Banff :.") = NON renseigne.
    champs = suggest_reporting_fields(
        "Rejet cellulaire aigu du greffon renal. Classification selon Banff :."
    )
    assert any("Banff" in c for c in champs)


def test_score_renseigne_pas_de_doublon():
    # Categorie de Paris deja renseignee -> ne pas re-proposer.
    champs = suggest_reporting_fields(
        "Cytologie urinaire. Categorie AUC (Systeme de Paris)."
    )
    assert champs == []


def test_pas_de_faux_positif_sur_tumoral_solide():
    # Une piece tumorale classique ne declenche AUCUN systeme cyto/medical.
    champs = suggest_reporting_fields(
        "Piece de tumorectomie, carcinome canalaire infiltrant du sein grade II."
    )
    assert champs == []


def test_crohn_pas_de_systeme_reporting():
    # Crohn n'a pas de systeme de reporting ici (gere par ailleurs) : pas de bruit.
    champs = suggest_reporting_fields("Biopsies coliques, maladie de crohn, granulome.")
    assert champs == []
