"""Formulations de reference du praticien : le matching doit etre VERROUILLE
par organe. Injecter le texte canonique d'un autre organe (ex un texte colique
sur une biopsie bronchique) serait pire que de n'injecter rien du tout.
"""

from reports.canonical_texts import build_canonical_block, find_canonical_texts


def test_match_dans_le_bon_organe():
    res = find_canonical_texts("hemorroides non compliquees", ["canal_anal"])
    assert res and "morro" in res[0]["lesion"].lower()


def test_pas_d_injection_sans_organe():
    # Sans organe reconnu -> aucune reference (verrou).
    assert find_canonical_texts("hemorroides non compliquees", []) == []
    assert find_canonical_texts("hemorroides", None) == []


def test_pas_de_fuite_inter_organes():
    # Une dictee pulmonaire ne doit JAMAIS recevoir un texte digestif.
    res = find_canonical_texts("muqueuse bronchique inflammatoire", ["poumon"])
    for entry in res:
        low = entry["lesion"].lower()
        assert "lieberkuhnien" not in low and "colique" not in low


def test_dictee_sans_lesion_connue_pas_de_match():
    assert find_canonical_texts("blablabla xyz sans lesion connue", ["poumon"]) == []
    assert find_canonical_texts("blablabla xyz", ["colon_rectum"]) == []


def test_bloc_precise_que_ce_sont_des_modeles():
    # Le bloc injecte DOIT rappeler que ce sont des modeles, pas des observations
    # (sinon le LLM recopierait des constatations non dictees).
    bloc = build_canonical_block("hemorroides non compliquees", ["canal_anal"])
    assert bloc
    assert "MODELES" in bloc and "A COMPLETER" in bloc


def test_bloc_vide_si_aucun_match():
    assert build_canonical_block("blablabla xyz", ["poumon"]) == ""
