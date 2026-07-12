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


def test_conclusion_todo_removed():
    # La conclusion ne doit PAS contenir de [A COMPLETER] : il est retire du texte.
    cr = "**Microscopie :**\nADK.\n**__CONCLUSION :__**\n**ADK [A COMPLETER: grade].**"
    r = _build(_payload(cr))
    conclusion = r.cr[r.cr.lower().rfind("conclusion"):]
    assert "a completer" not in conclusion.lower()


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


def test_filter_grade_sbr_dropped_on_precancer_but_keeps_nuclear_grade():
    # CCIS (in situ) : le grade SBR/Elston du carcinome INFILTRANT ne s'applique
    # pas, mais le grade NUCLEAIRE de l'in situ reste legitime.
    alertes = [_alerte("Grade SBR/Elston"), _alerte("Grade nucleaire du CCIS"),
               _alerte("Statut RE")]
    kept, _ = filter_alertes(alertes, ["sein"], SpecimenType.PIECE_OPERATOIRE, "pre_cancereux")
    champs = [a.champ for a in kept]
    assert "Grade SBR/Elston" not in champs
    assert "Grade nucleaire du CCIS" in champs
    assert "Statut RE" in champs


def test_forbidden_marker_stripped_from_cr_body():
    # Marqueur "emboles" (invasif) dans le corps d'un CR in situ -> retire du texte.
    cr = ("**Microscopie :**\nCarcinome canalaire in situ de haut grade.\n"
          "- Emboles vasculaires : [A COMPLETER: etude des emboles]\n"
          "- Taille du CCIS : [A COMPLETER: taille en mm]\n"
          "**__CONCLUSION :__**\n**CCIS haut grade.**")
    r = _build(_payload(cr, organe="sein", tp="piece_operatoire"), organes=["sein"])
    assert "embole" not in r.cr.lower()       # champ invasif retire
    assert "taille" in r.cr.lower()           # champ legitime conserve


# --- Fidelite inverse : mesures dictees perdues (B5) ---------------------

def test_taille_dictee_perdue_remonte_au_panel():
    from reports.guardrails import _check_dropped_measurements

    w, a = _check_dropped_measurements(
        "Masse renale. [A COMPLETER: taille tumorale].",
        "Masse renale de 11 cm au pole superieur.",
    )
    assert w and any("11 cm" in x for x in w)
    assert a and any("11 cm" in x.champ for x in a)


def test_taille_conservee_pas_de_bruit():
    from reports.guardrails import _check_dropped_measurements

    w, a = _check_dropped_measurements(
        "Masse renale de 11 cm.", "Masse renale de 11 cm."
    )
    assert w == [] and a == []


def test_taille_en_lettres_reconnue():
    from reports.guardrails import _check_dropped_measurements

    # "trois centimetres" (dictee) -> "3 cm" (CR) ne doit pas alerter.
    w, _ = _check_dropped_measurements("Nodule de 3 cm.", "Nodule de trois centimetres.")
    assert w == []


# --- Marqueurs moleculaires tumoraux hors carcinome infiltrant -----------

def _dm(champ):
    from models import DonneeManquante
    return DonneeManquante(champ=champ, description="", section="x")


def test_mmr_retire_sur_adenome_pre_cancereux():
    from reports.guardrails import filter_alertes
    from specimen_type import SpecimenType

    kept, _ = filter_alertes(
        [_dm("statut MMR"), _dm("Type histologique")],
        ["colon_rectum"], SpecimenType.BIOPSIE, "pre_cancereux",
    )
    champs = [k.champ for k in kept]
    assert "statut MMR" not in champs
    assert "Type histologique" in champs


def test_mmr_conserve_sur_carcinome_infiltrant():
    from reports.guardrails import filter_alertes
    from specimen_type import SpecimenType

    kept, _ = filter_alertes(
        [_dm("statut MMR/MSI")], ["colon_rectum"],
        SpecimenType.PIECE_OPERATOIRE, "infiltrant",
    )
    assert [k.champ for k in kept] == ["statut MMR/MSI"]


def test_pas_de_collision_de_mot_msi():
    from reports.guardrails import _has_word, _MOLECULAR_TUMORAL_TERMS

    assert not _has_word("transmission synaptique", _MOLECULAR_TUMORAL_TERMS)
    assert _has_word("instabilite des microsatellites", _MOLECULAR_TUMORAL_TERMS)
