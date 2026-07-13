"""Securite : detection deterministe de la SURSTADIFICATION ganglionnaire.

Ce test aurait attrape le bug clinique reel : sur une dictee ou tous les
ganglions sont "indemnes", le modele avait ecrit "ganglion envahi" (N0 -> N+).
Le garde-fou signale toute atteinte ganglionnaire AFFIRMEE mais absente de la
dictee, sans reecrire le texte a l'aveugle.
"""

from reports.guardrails import _check_nodal_overinterpretation


def test_atteinte_inventee_est_signalee():
    # Le CR affirme un envahissement absent de la dictee -> alerte.
    source = (
        "Curage ganglionnaire, sept ganglions de la loge de Barety. "
        "Les 26 ganglions sont indemnes de lesion metastatique."
    )
    cr = (
        "**Microscopie :**\nUn ganglion est envahi par la tumeur.\n"
        "**CONCLUSION :**\nAdenocarcinome avec metastase ganglionnaire."
    )
    warnings, alertes = _check_nodal_overinterpretation(cr, source)
    assert warnings, "une atteinte ganglionnaire inventee doit etre signalee"
    assert alertes and "confirmer" in alertes[0].champ.lower()


def test_negation_non_signalee():
    # "sans metastase ganglionnaire" est une negation -> aucune alerte.
    source = "Les 26 ganglions sont indemnes."
    cr = "**CONCLUSION :**\nAdenocarcinome de 18 mm, sans metastase ganglionnaire (0/26)."
    warnings, alertes = _check_nodal_overinterpretation(cr, source)
    assert warnings == [] and alertes == []


def test_atteinte_dictee_non_signalee():
    # L'atteinte est DICTEE -> le CR a le droit de l'affirmer, pas d'alerte.
    source = "Deux ganglions sur douze sont envahis par l'adenocarcinome."
    cr = "**CONCLUSION :**\nAdenocarcinome avec metastase ganglionnaire (2/12), pN1."
    warnings, alertes = _check_nodal_overinterpretation(cr, source)
    assert warnings == [] and alertes == []


def test_pas_de_ganglion_pas_d_alerte():
    source = "Biopsie cutanee, dermatose inflammatoire."
    cr = "**CONCLUSION :**\nDermatose inflammatoire benigne."
    warnings, alertes = _check_nodal_overinterpretation(cr, source)
    assert warnings == [] and alertes == []
