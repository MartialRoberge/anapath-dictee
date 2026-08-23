"""Contenu des questionnaires de l'etude.

Deux choses se defendent ici : la cotation du F-SUS, qui doit etre exacte pour
que le score se compare a la litterature, et les items que le cahier interdit
de retirer.
"""

from etude.questionnaires import (
    CATALOGUE,
    FSUS_ITEMS,
    ORDRE_DE_RETRAIT_PAR_CAS,
    PAR_CAS,
    fsus_pret,
    score_fsus,
)
from etude.vocabulaire import QUESTIONNAIRES


def _fsus(reponses: list[int]) -> dict[str, int]:
    return {f"fsus_{rang:02d}": valeur for rang, valeur in enumerate(reponses, start=1)}


# --- Le F-SUS ---------------------------------------------------------------


def test_le_fsus_n_est_pas_pret_tant_qu_il_n_est_pas_recopie():
    """Retraduire soi-meme detruit ce qui rend le score comparable : un F-SUS
    paraphrase n'est plus un F-SUS. Tant que les libelles publies ne sont pas
    en place, le questionnaire de fin d'etude ne doit pas etre servi."""
    assert not fsus_pret()


def test_la_polarite_du_fsus_est_alternee():
    """Impairs positifs, pairs negatifs : c'est la structure de l'instrument,
    et la cotation en depend."""
    assert [item.inverse for item in FSUS_ITEMS[:4]] == [False, True, False, True]
    assert len(FSUS_ITEMS) == 10


def test_le_score_fsus_maximal_vaut_cent():
    """Tout a fait d'accord sur les items positifs, pas du tout sur les
    negatifs."""
    assert score_fsus(_fsus([5, 1, 5, 1, 5, 1, 5, 1, 5, 1])) == 100.0


def test_le_score_fsus_minimal_vaut_zero():
    assert score_fsus(_fsus([1, 5, 1, 5, 1, 5, 1, 5, 1, 5])) == 0.0


def test_un_fsus_neutre_vaut_cinquante():
    assert score_fsus(_fsus([3] * 10)) == 50.0


def test_un_item_manquant_rend_le_score_incalculable():
    """Mieux vaut None qu'un score partiel qu'on prendrait pour un score
    complet."""
    partiel = _fsus([3] * 10)
    del partiel["fsus_07"]
    assert score_fsus(partiel) is None


def test_une_reponse_hors_echelle_rend_le_score_incalculable():
    assert score_fsus(_fsus([3, 3, 3, 3, 3, 3, 3, 3, 3, 9])) is None


# --- Le questionnaire par cas ----------------------------------------------


def test_l_item_d_explicabilite_ne_se_retire_jamais():
    """Il n'a pas de substitut : aucune telemetrie ne dit si le praticien a
    COMPRIS. Le cahier interdit son retrait meme pour raccourcir."""
    assert "par_cas_04" not in ORDRE_DE_RETRAIT_PAR_CAS
    item = next(i for i in PAR_CAS.items if i.id == "par_cas_04")
    assert item.obligatoire


def test_la_question_d_omission_est_obligatoire():
    """Un oubli ne laisse aucune trace dans la telemetrie : c'est la seule
    chose que l'instrumentation ne peut pas voir toute seule."""
    item = next(i for i in PAR_CAS.items if i.id == "par_cas_00")
    assert item.obligatoire


def test_l_item_de_correction_est_marque_inverse():
    """Sans ce marquage, la cotation additionnerait un item negatif comme s'il
    etait positif et le score par cas serait faux."""
    item = next(i for i in PAR_CAS.items if i.id == "par_cas_02")
    assert item.inverse


def test_le_questionnaire_par_cas_reste_court():
    """40 secondes annoncees : au-dela, le praticien repond n'importe quoi ou
    abandonne l'etude."""
    assert PAR_CAS.duree_estimee_s <= 60
    assert len(PAR_CAS.items) <= 10


# --- Coherence du catalogue -------------------------------------------------


def test_le_catalogue_couvre_les_trois_questionnaires():
    assert set(CATALOGUE) == set(QUESTIONNAIRES)


def test_les_identifiants_d_items_sont_uniques():
    """Un doublon ferait silencieusement ecraser une reponse par une autre."""
    for questionnaire in CATALOGUE.values():
        identifiants = [item.id for item in questionnaire.items]
        assert len(identifiants) == len(set(identifiants)), questionnaire.nom


def test_tout_item_conditionnel_pointe_vers_un_item_existant():
    """Un renvoi casse afficherait la question a tout le monde, ou a personne."""
    connus = {
        item.id for questionnaire in CATALOGUE.values() for item in questionnaire.items
    }
    for questionnaire in CATALOGUE.values():
        for item in questionnaire.items:
            if item.depend_de is not None:
                assert item.depend_de in connus, f"{item.id} -> {item.depend_de}"


# --- Les ancres d'echelle ---------------------------------------------------


def test_chaque_echelle_porte_ses_ancres():
    """Sans ancres, deux praticiens cotent en sens inverse et rien ne le revele
    au depouillement. Le F-SUS fait exception : les siennes se recopient depuis
    la source publiee, comme ses libelles."""
    for questionnaire in CATALOGUE.values():
        for item in questionnaire.items:
            if item.type not in ("likert_5", "echelle_10"):
                continue
            if item.id.startswith("fsus_"):
                continue
            assert item.ancre_basse, item.id
            assert item.ancre_haute, item.id


def test_le_pdqi9_n_est_pas_cote_en_accord():
    """Le PDQI-9 cote un DEGRE de qualite documentaire. Le coter en accord
    change la question posee : c'est la meme faute que retraduire le F-SUS."""
    pdqi = [i for i in CATALOGUE["fin_etude"].items if i.id.startswith("pdqi_")]
    assert len(pdqi) == 9
    for item in pdqi:
        assert "accord" not in item.ancre_basse.lower()
        assert "accord" not in item.ancre_haute.lower()


def test_les_items_par_cas_sont_cotes_en_accord():
    """Ce sont des AFFIRMATIONS : 'la proposition correspondait a ce que j'ai
    dicte'. L'accord est la bonne echelle pour celles-la."""
    item = next(i for i in PAR_CAS.items if i.id == "par_cas_01")
    assert "accord" in item.ancre_basse.lower()


def test_un_item_formule_en_question_n_est_pas_cote_en_accord():
    """'Faites-vous confiance a ... ?' n'appelle pas 'tout a fait d'accord'."""
    item = next(i for i in CATALOGUE["inclusion"].items if i.id == "inclusion_14")
    assert "accord" not in item.ancre_basse.lower()
