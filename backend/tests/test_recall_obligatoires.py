"""Rappel déterministe des champs obligatoires INCa — recall SANS faux positif.

Vérifie que les champs pronostiques réglementaires absents sont bien rappelés,
et QUE le rappel reste spécifique au type de prélèvement et à la nature de la
lésion (pas de champ pièce sur biopsie, pas de champ tumoral sur bénin).
"""

from reports.engine import GeneratedReport
from reports.panel import build_panel as _build_panel


def _panel(cr, organe, tp, organes):
    r = GeneratedReport(cr=cr, organe=organe, type_prelevement=tp, alertes=[],
                        warnings=[], organes_detectes=organes)
    return [p.champ for p in _build_panel(r)]


def test_recall_prostate_biopsie_pas_de_champ_piece():
    cr = ("**__EXAMEN ANATOMOPATHOLOGIQUE DE BIOPSIES PROSTATIQUES__**\n"
          "**Microscopie :**\nAdenocarcinome, score de Gleason 7 (3+4).\n"
          "**__CONCLUSION :__**\n**Adenocarcinome, Gleason 7.**")
    champs = " | ".join(_panel(cr, "prostate", "biopsie", ["prostate"])).lower()
    # Champs pièce interdits sur biopsie
    assert "ptnm" not in champs
    assert "marges" not in champs
    assert "vesicule" not in champs and "seminale" not in champs
    assert "extraprostatique" not in champs


def test_recall_prostate_piece_inclut_staging():
    cr = ("**__EXAMEN DE PROSTATECTOMIE RADICALE__**\n**Microscopie :**\n"
          "Adenocarcinome, score de Gleason 7.\n**__CONCLUSION :__**\n**ADK.**")
    champs = " | ".join(_panel(cr, "prostate", "piece_operatoire", ["prostate"])).lower()
    assert "ptnm" in champs
    assert "marges" in champs


def test_recall_endometre_inclut_mmr_msi():
    cr = ("**__EXAMEN DE HYSTERECTOMIE__**\n**Microscopie :**\n"
          "Adenocarcinome endometrioide infiltrant le myometre, grade 1.\n"
          "**__CONCLUSION :__**\n**ADK endometrioide infiltrant.**")
    champs = " | ".join(_panel(cr, "endometre", "piece_operatoire", ["endometre"])).lower()
    assert "mmr" in champs or "msi" in champs


def test_recall_benin_aucun_champ_tumoral():
    # Gastrite bénigne : le rappel ne doit ajouter AUCUN champ tumoral.
    cr = ("**__EXAMEN ANATOMOPATHOLOGIQUE DE BIOPSIES GASTRIQUES__**\n"
          "**Microscopie :**\nGastrite chronique avec infiltrat inflammatoire, "
          "Helicobacter pylori present.\n**__CONCLUSION :__**\n**Gastrite chronique.**")
    champs = " | ".join(_panel(cr, "estomac", "biopsie", ["estomac"])).lower()
    for interdit in ("ptnm", "gleason", "sbr", "breslow", "embole", "grade histopronostique"):
        assert interdit not in champs, f"champ tumoral '{interdit}' sur lésion bénigne"
