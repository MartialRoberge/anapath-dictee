"""Contrat du masquage de negation (source unique adicap/snomed/specimen_type)."""

from negation import mask_negations, NEGATION_MARKERS


def test_masque_la_clause_niee_conserve_le_reste():
    src = "adenocarcinome, absence de metastase ganglionnaire."
    out = mask_negations(src)
    assert "adenocarcinome" in out          # affirmation conservee
    assert "metastase" not in out           # clause niee masquee


def test_masque_s_arrete_au_separateur():
    # La negation ne doit masquer que sa propre phrase.
    src = "pas de tumeur. carcinome infiltrant present."
    out = mask_negations(src)
    assert "tumeur" not in out
    assert "carcinome infiltrant present" in out


def test_preserve_les_positions():
    # Le masque remplace par des espaces -> meme longueur (offsets stables).
    src = "sans signe de malignite ; lesion benigne"
    assert len(mask_negations(src)) == len(src)


def test_marqueurs_partages_non_vides():
    assert "absence de" in NEGATION_MARKERS
    assert "pas de" in NEGATION_MARKERS
