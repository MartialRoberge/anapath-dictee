"""Tests du validateur de cohérence médicale (exécuté à chaque génération)."""

from reports.coherence import assess_coherence


def test_cr_complet_est_coherent():
    cr = (
        "**__BIOPSIE DU SEIN GAUCHE__**\n"
        "**Macroscopie :**\nUne carotte de 5 mm.\n"
        "**Microscopie :**\nCarcinome canalaire infiltrant, grade SBR 2.\n"
        "**__CONCLUSION :__**\n**Carcinome canalaire infiltrant, grade SBR 2.**"
    )
    r = assess_coherence(cr)
    assert r.ok
    assert r.structure_complete
    assert set(r.sections_presentes) >= {"titre", "microscopie", "conclusion"}


def test_conclusion_absente_bloquant():
    cr = "**__BIOPSIE__**\n**Microscopie :**\nADK."
    r = assess_coherence(cr)
    assert not r.ok
    assert any(i.code == "conclusion_absente" for i in r.issues)


def test_microscopie_absente_signalee():
    cr = "**__BIOPSIE__**\n**__CONCLUSION :__**\n**Diagnostic final.**"
    r = assess_coherence(cr)
    assert any(i.code == "microscopie_absente" for i in r.issues)
    assert not r.structure_complete


def test_chiffre_conclusion_absent_du_corps_signale():
    # La conclusion cite "42 mm" mais le corps ne le contient pas -> incohérence.
    cr = (
        "**__PIECE__**\n**Microscopie :**\nAdenocarcinome.\n"
        "**__CONCLUSION :__**\n**Adenocarcinome de 42 mm.**"
    )
    r = assess_coherence(cr)
    assert any(i.code == "chiffre_conclusion_absent_corps" for i in r.issues)


def test_chiffre_conclusion_present_dans_corps_ok():
    cr = (
        "**__PIECE__**\n**Microscopie :**\nAdenocarcinome mesurant 18 mm.\n"
        "**__CONCLUSION :__**\n**Adenocarcinome de 18 mm.**"
    )
    r = assess_coherence(cr)
    assert not any(i.code == "chiffre_conclusion_absent_corps" for i in r.issues)


def test_todo_dans_conclusion_signale():
    cr = (
        "**__BIOPSIE__**\n**Microscopie :**\nADK.\n"
        "**__CONCLUSION :__**\n**ADK [A COMPLETER: grade].**"
    )
    r = assess_coherence(cr)
    assert any(i.code == "todo_conclusion" for i in r.issues)


def test_dictee_non_medicale_est_coherente():
    cr = "**La transcription ne semble pas correspondre a un compte-rendu anatomopathologique.**"
    r = assess_coherence(cr)
    assert r.ok
