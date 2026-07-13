"""Contrat de la normalisation de texte (source unique tout le backend)."""

from text_utils import strip_accents, normaliser, cle_alphanum


def test_strip_accents_preserve_la_casse():
    assert strip_accents("Épithélium Malpighien") == "Epithelium Malpighien"


def test_normaliser_minuscule_et_sans_accents():
    assert normaliser("Côlon-Rectum") == "colon-rectum"
    assert normaliser("À PRÉCISER") == "a preciser"


def test_normaliser_ligatures_francaises():
    # Le NFD seul perdrait "oe"/"ae" : on les developpe explicitement.
    assert normaliser("Œsophage") == "oesophage"
    assert normaliser("œsophage") == "oesophage"
    assert normaliser("CŒUR") == "coeur"


def test_cle_alphanum_ignore_ponctuation_et_espaces():
    assert cle_alphanum("pT3, pN1 (8e éd.)") == "pt3pn18eed"
    assert cle_alphanum("Statut  MMR / MSI") == "statutmmrmsi"


def test_idempotence():
    for f in (strip_accents, normaliser, cle_alphanum):
        once = f("Adénocarcinome lépidique")
        assert f(once) == once
