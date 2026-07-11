"""Tests de la détection automatique multi-organes et de l'injection de contexte."""

from reports.knowledge import build_context_block, detect_organs


def _organ_ids(transcript: str) -> list[str]:
    return [t.organe for t in detect_organs(transcript)]


# -- détection mono-organe -------------------------------------------------


def test_detect_lung_biopsy():
    assert "poumon" in _organ_ids("biopsie pulmonaire, carotte, adenocarcinome TTF1")


def test_detect_melanoma():
    assert _organ_ids("melanome cutane du dos, Breslow 1.2 mm, ulceration") == [
        "melanome"
    ]


def test_detect_prostate():
    assert "prostate" in _organ_ids("prostatectomie, score de Gleason 7, ISUP 2")


# -- pas de faux positifs (le point critique) ------------------------------


def test_no_false_positive_cin_in_adenocarcinome():
    # "adenocarCINome" ne doit pas déclencher col_uterin (mot-clé "CIN").
    assert "col_uterin" not in _organ_ids("adenocarcinome pulmonaire TTF1 positif")


def test_curage_ganglionnaire_not_lymphome():
    # Un curage ganglionnaire d'une pièce pulmonaire n'est PAS un lymphome.
    ids = _organ_ids("piece de lobectomie pulmonaire avec curage ganglionnaire")
    assert "lymphome" not in ids
    assert "poumon" in ids


def test_lobectomie_not_foie():
    # "lobectomie" (pulmonaire) ne doit pas déclencher le foie.
    assert "foie" not in _organ_ids("lobectomie pulmonaire, adenocarcinome")


def test_adenopathie_cervicale_not_col_uterin():
    # "adénopathie cervicale" = ganglion du cou, pas le col de l'utérus.
    ids = _organ_ids("biopsie adenopathie cervicale, lymphome B, CD20 positif")
    assert "col_uterin" not in ids
    assert "lymphome" in ids


def test_col_uterin_specific_still_detected():
    assert "col_uterin" in _organ_ids("biopsie du col uterin, CIN 3, p16")


# -- multi-organes ---------------------------------------------------------


def test_multi_organ_biopsies_etagees():
    ids = _organ_ids("biopsies etagees oesophage bas, estomac antre")
    assert "oesophage" in ids
    assert "estomac" in ids


def test_context_block_multi_mentions_all():
    ctx = build_context_block("biopsies oesophage et estomac")
    assert "PLUSIEURS ORGANES" in ctx.block
    assert "Estomac" in ctx.block
    assert "Œsophage" in ctx.block or "sophage" in ctx.block


# -- contenu du bloc -------------------------------------------------------


def test_context_block_has_classification():
    ctx = build_context_block("melanome cutane, Breslow")
    assert "melanome" in ctx.organes
    assert "Breslow" in ctx.block or "Mélanome" in ctx.block


def test_empty_when_no_organ():
    ctx = build_context_block("bonjour test micro un deux trois")
    assert ctx.organes == []
    assert ctx.block == ""


def test_specimen_detected():
    ctx = build_context_block("biopsie du sein, carcinome canalaire infiltrant")
    assert ctx.specimen.value == "biopsie"
