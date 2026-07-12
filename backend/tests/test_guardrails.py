"""Tests des guardrails de generation."""

import json

import pytest

from reports.guardrails import (
    GenerationParseError,
    build_validated_report,
    filter_alertes,
    parse_llm_json,
)
from specimen_type import SpecimenType
from models import DonneeManquante


def _payload(cr: str, organe="poumon", tp="biopsie", alertes=None):
    return json.dumps(
        {"cr": cr, "organe": organe, "type_prelevement": tp, "alertes": alertes or []},
        ensure_ascii=False,
    )


def _build(payload, source="x", organes=None):
    return build_validated_report(
        payload, source_text=source, organes=organes or [],
        provider="fake", model="m",
    )


# -- parsing ---------------------------------------------------------------


def test_parse_plain_json():
    assert parse_llm_json('{"cr": "x"}')["cr"] == "x"


def test_parse_with_markdown_fence():
    raw = '```json\n{"cr": "x", "organe": "poumon"}\n```'
    assert parse_llm_json(raw)["organe"] == "poumon"


def test_parse_with_surrounding_text():
    raw = 'Voici le resultat : {"cr": "x"} merci.'
    assert parse_llm_json(raw)["cr"] == "x"


def test_parse_invalid_raises():
    with pytest.raises(GenerationParseError):
        parse_llm_json("pas de json ici")


def test_missing_cr_raises():
    with pytest.raises(GenerationParseError):
        _build(_payload(""))


# -- garde-chiffres --------------------------------------------------------


def test_number_guard_flags_hallucinated_measure():
    cr = "**Microscopie :**\nLesion de 42 mm.\n**__CONCLUSION :__**\n**ADK.**"
    r = _build(_payload(cr), source="lesion sans taille dictee")
    assert any("42" in w for w in r.warnings)


def test_number_guard_accepts_spelled_source():
    cr = "**Macroscopie :**\nCarotte de 5 mm.\n**__CONCLUSION :__**\n**ADK.**"
    r = _build(_payload(cr), source="carotte de cinq millimetres")
    assert not any("5" in w and "mm" in w for w in r.warnings)


def test_number_guard_ignores_bloc_numbering():
    cr = "**Macroscopie :**\nInclusion en 3 blocs.\n**__CONCLUSION :__**\n**RAS.**"
    r = _build(_payload(cr), source="pas de nombre")
    assert not any("bloc" in w.lower() for w in r.warnings)


# -- negation --------------------------------------------------------------


def test_negation_guard_flags_pas_de_cellule_normale():
    cr = "**Etude cytologique :**\npas de cellule normale.\n**__CONCLUSION :__**\n**RAS.**"
    r = _build(_payload(cr, tp="cytologie"), source="il n'y a pas de cellule normale")
    assert any("normale" in w for w in r.warnings)


def test_verifier_marker_surfaced():
    cr = "**Microscopie :**\n[VERIFIER: negation ambigue].\n**__CONCLUSION :__**\n**RAS.**"
    r = _build(_payload(cr))
    assert any("VERIFIER" in w for w in r.warnings)


# -- perimetre biopsie -----------------------------------------------------


def test_biopsy_scope_flags_ptnm():
    cr = "**Microscopie :**\nADK, pTNM pT2, marges de resection saines.\n**__CONCLUSION :__**\n**ADK.**"
    r = _build(_payload(cr, tp="biopsie"), source="biopsie adk")
    assert any("piece operatoire" in w.lower() for w in r.warnings)


def test_piece_operatoire_allows_ptnm():
    cr = "**Microscopie :**\nADK, pTNM pT2.\n**__CONCLUSION :__**\n**ADK pT2.**"
    r = _build(_payload(cr, tp="piece_operatoire"), source="piece pt2")
    assert not any("hors perimetre" in w.lower() for w in r.warnings)


# -- conclusion ------------------------------------------------------------


def test_conclusion_todo_flagged():
    cr = "**Microscopie :**\nADK.\n**__CONCLUSION :__**\n**ADK [A COMPLETER: grade].**"
    r = _build(_payload(cr))
    assert any("conclusion" in w.lower() for w in r.warnings)


# -- garde recommandation hors contexte (anti-erreur medicale) -------------


def test_breslow_without_melanoma_flagged():
    # Breslow cité alors qu'aucun mélanome détecté -> recommandation hors contexte.
    cr = "**Microscopie :**\nADK pulmonaire, indice de Breslow 2 mm.\n**__CONCLUSION :__**\n**ADK.**"
    r = _build(_payload(cr, organe="poumon"), organes=["poumon"])
    assert any("breslow" in w.lower() for w in r.warnings)


def test_breslow_with_melanoma_ok():
    cr = "**Microscopie :**\nMelanome, indice de Breslow 2 mm.\n**__CONCLUSION :__**\n**Melanome.**"
    r = _build(_payload(cr, organe="melanome"), organes=["melanome"])
    assert not any("breslow" in w.lower() for w in r.warnings)


def test_gleason_without_prostate_flagged():
    cr = "**Microscopie :**\nLesion mammaire, score de Gleason 7.\n**__CONCLUSION :__**\n**x.**"
    r = _build(_payload(cr, organe="sein"), organes=["sein"])
    assert any("gleason" in w.lower() for w in r.warnings)


def test_sbr_with_breast_ok():
    cr = "**Microscopie :**\nCarcinome canalaire, grade SBR II.\n**__CONCLUSION :__**\n**CCI grade II.**"
    r = _build(_payload(cr, organe="sein"), organes=["sein"])
    assert not any("sbr" in w.lower() and "hors contexte" in w.lower() for w in r.warnings)


# -- garde derivation TNM (anti-sous-stadification) ------------------------


def test_tnm_derivation_flagged_when_not_dictated():
    cr = "**Microscopie :**\nAdenocarcinome infiltrant la sous-sereuse.\n**__CONCLUSION :__**\n**Adenocarcinome pT3 pN1b.**"
    r = _build(_payload(cr, tp="piece_operatoire"), source="adenocarcinome du colon, 2 ganglions envahis")
    assert any("pt3" in w.lower() or "pn1b" in w.lower() or "stade" in w.lower() for w in r.warnings)


def test_tnm_not_flagged_when_dictated():
    cr = "**Microscopie :**\nAdenocarcinome.\n**__CONCLUSION :__**\n**Adenocarcinome pT3 pN1b.**"
    r = _build(_payload(cr, tp="piece_operatoire"), source="adenocarcinome colique classe pT3 pN1b par le chirurgien")
    assert not any("stadification" in w.lower() for w in r.warnings)


# -- champs de base --------------------------------------------------------


def _alerte(champ, desc=""):
    return DonneeManquante(champ=champ, description=desc, section="microscopie")


def test_filter_drops_wrong_organ_classification():
    alertes = [_alerte("Indice de Breslow"), _alerte("Degre de differenciation")]
    kept, dropped = filter_alertes(alertes, ["colon_rectum"], SpecimenType.PIECE_OPERATOIRE)
    champs = [a.champ for a in kept]
    assert "Indice de Breslow" not in champs
    assert "Degre de differenciation" in champs
    assert dropped


def test_filter_drops_gleason_outside_prostate():
    alertes = [_alerte("Score de Gleason")]
    kept, _ = filter_alertes(alertes, ["sein"], SpecimenType.BIOPSIE)
    assert kept == []


def test_filter_keeps_gleason_for_prostate():
    alertes = [_alerte("Score de Gleason / ISUP")]
    kept, _ = filter_alertes(alertes, ["prostate"], SpecimenType.BIOPSIE)
    assert len(kept) == 1


def test_filter_drops_piece_fields_on_biopsy():
    alertes = [_alerte("Statut pTNM"), _alerte("Marges de resection"), _alerte("Grade SBR")]
    kept, dropped = filter_alertes(alertes, ["sein"], SpecimenType.BIOPSIE)
    champs = [a.champ for a in kept]
    assert "Grade SBR" in champs
    assert "Statut pTNM" not in champs
    assert "Marges de resection" not in champs


def test_filter_keeps_piece_fields_on_piece():
    alertes = [_alerte("Statut pTNM"), _alerte("Marges de resection")]
    kept, _ = filter_alertes(alertes, ["colon_rectum"], SpecimenType.PIECE_OPERATOIRE)
    assert len(kept) == 2


def test_filter_tumoral_field_dropped_on_benign():
    # Lésion bénigne : aucun champ tumoral (grade, stade, mitoses, emboles).
    alertes = [_alerte("Grade histopronostique SBR"), _alerte("Index mitotique"),
               _alerte("Emboles vasculaires"), _alerte("Type histologique")]
    kept, dropped = filter_alertes(alertes, ["colon_rectum"], SpecimenType.BIOPSIE, "benin")
    champs = [a.champ for a in kept]
    assert "Type histologique" in champs
    assert "Grade histopronostique SBR" not in champs
    assert "Index mitotique" not in champs
    assert "Emboles vasculaires" not in champs
    assert len(dropped) == 3


def test_filter_tumoral_field_kept_on_infiltrant():
    alertes = [_alerte("Grade histopronostique SBR"), _alerte("Statut pTNM")]
    kept, _ = filter_alertes(alertes, ["sein"], SpecimenType.PIECE_OPERATOIRE, "infiltrant")
    assert len(kept) == 2


def test_filter_invasive_field_dropped_on_precancer():
    alertes = [_alerte("Statut pTNM"), _alerte("Grade de dysplasie")]
    kept, _ = filter_alertes(alertes, ["col_uterin"], SpecimenType.BIOPSIE, "pre_cancereux")
    champs = [a.champ for a in kept]
    assert "Grade de dysplasie" in champs
    assert "Statut pTNM" not in champs


def test_filter_indetermine_context_does_not_over_filter():
    # Contexte indéterminé -> on ne filtre pas par nature de lésion.
    alertes = [_alerte("Grade histopronostique")]
    kept, _ = filter_alertes(alertes, ["sein"], SpecimenType.BIOPSIE, "indetermine")
    assert len(kept) == 1


def test_filter_no_organ_keeps_all():
    # Sans organe détecté, on ne filtre pas par classification (mais piece-only reste).
    alertes = [_alerte("Indice de Breslow")]
    kept, _ = filter_alertes(alertes, [], SpecimenType.PIECE_OPERATOIRE)
    assert len(kept) == 1


def test_report_fields_populated():
    r = build_validated_report(
        _payload("**Micro :** x", organe="canal anal", tp="biopsie"),
        source_text="x", organes=["canal_anal"], provider="mistral", model="m-large",
    )
    assert r.organe == "canal anal"
    assert r.type_prelevement == "biopsie"
    assert r.provider == "mistral"
    assert r.organes_detectes == ["canal_anal"]
