"""Cohérence du panneau de conseils : ZÉRO faux positif.

Un champ ne doit JAMAIS être signalé "manquant" s'il est déjà présent/dicté dans
le CR — quel que soit ce que le LLM (probabiliste) a listé dans ses alertes.
On simule des alertes LLM contenant à la fois des champs présents et absents,
et on vérifie que la vérification déterministe supprime tous les présents.
"""

import json

from reports.guardrails import build_validated_report, filter_present_alertes
from models import DonneeManquante


def _a(champ):
    return DonneeManquante(champ=champ, description="", section="microscopie")


# (CR, champs PRÉSENTS dans le CR, champs réellement ABSENTS)
CASES = [
    (
        "Carcinome canalaire infiltrant, grade SBR 2. RE positif, HER2 negatif.",
        ["Grade SBR", "Statut HER2", "Recepteurs oestrogenes (RE)"],
        ["Emboles vasculaires", "Index Ki67"],
    ),
    (
        "Adenocarcinome pulmonaire d'architecture acineuse, TTF1 positif, ALK negatif.",
        ["Architecture", "Statut TTF1", "Statut ALK"],
        ["Statut PD-L1", "Mutation EGFR"],
    ),
    (
        "Melanome, indice de Breslow 1.5 mm, ulceration presente, 3 mitoses.",
        ["Indice de Breslow", "Ulceration", "Index mitotique"],
        ["Emboles vasculaires", "Marges laterales"],
    ),
    (
        "Adenocarcinome prostatique, score de Gleason 7 (3+4).",
        ["Score de Gleason"],
        ["Engainement perinerveux", "Extension extraprostatique"],
    ),
    (
        "Adenocarcinome colique moyennement differencie infiltrant la sous-sereuse. "
        "18 ganglions examines dont 2 metastatiques. Marges saines.",
        ["Degre de differenciation", "Ganglions examines", "Marges de resection"],
        ["Emboles vasculaires", "Engainement perinerveux"],
    ),
]


def test_zero_faux_positif_sur_champs_presents():
    total_present = 0
    faux_positifs = 0
    for cr, presents, _absents in CASES:
        alertes = [_a(c) for c in presents]
        kept, _ = filter_present_alertes(alertes, cr)
        total_present += len(presents)
        faux_positifs += len(kept)  # tout champ présent encore listé = faux positif
    assert faux_positifs == 0, (
        f"{faux_positifs}/{total_present} faux positifs (champs présents signalés manquants)"
    )


def test_vrais_manquants_conserves():
    for cr, _presents, absents in CASES:
        alertes = [_a(c) for c in absents]
        kept, _ = filter_present_alertes(alertes, cr)
        champs_kept = {a.champ for a in kept}
        for champ in absents:
            assert champ in champs_kept, f"'{champ}' (absent) a été perdu pour: {cr[:40]}"


def test_pipeline_complet_melange_present_absent():
    # Le LLM liste PRÉSENTS + ABSENTS ; le pipeline ne garde que les absents.
    for cr, presents, absents in CASES:
        alertes = [
            {"champ": c, "description": "preciser", "section": "microscopie",
             "raison": "test"}
            for c in presents + absents
        ]
        payload = json.dumps(
            {"cr": f"**Microscopie :**\n{cr}\n**__CONCLUSION :__**\n**Diagnostic.**",
             "organe": "sein", "type_prelevement": "piece_operatoire", "alertes": alertes},
            ensure_ascii=False,
        )
        r = build_validated_report(
            payload, source_text=cr, organes=["sein"], provider="f", model="m"
        )
        champs_finaux = {a.champ for a in r.alertes}
        for p in presents:
            assert p not in champs_finaux, f"faux positif: '{p}' présent mais signalé"
