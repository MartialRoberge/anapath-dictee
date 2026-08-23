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
from etude.vocabulaire import QUESTIONNAIRES, periodique_du


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
    """Il n'a pas de substitut : la telemetrie sait si un panneau a ete ouvert,
    jamais si le praticien a COMPRIS. Le cahier interdit son retrait meme pour
    raccourcir."""
    item = next(i for i in PAR_CAS.items if "compris pourquoi" in i.libelle)
    assert item.id not in ORDRE_DE_RETRAIT_PAR_CAS
    assert item.obligatoire


def test_la_question_d_omission_est_obligatoire():
    """Un oubli ne laisse aucune trace dans la telemetrie : c'est la seule
    chose que l'instrumentation ne peut pas voir toute seule."""
    item = next(i for i in PAR_CAS.items if i.id == "par_cas_00")
    assert item.obligatoire


def test_l_attestation_de_fin_est_obligatoire():
    """Sans elle, on ne sait pas si le praticien SIGNERAIT ce compte rendu — et
    un CR valide dans une etude mais qu'on ne signerait pas en routine ne prouve
    rien de ce que l'etude pretend montrer."""
    item = next(i for i in PAR_CAS.items if "validerais" in i.libelle)
    assert item.obligatoire
    assert item.type == "oui_non"


def test_l_erreur_introduite_est_demandee():
    """Une erreur que le systeme a AFFIRMEE sans la soumettre echappe a toute
    decision, donc a toute telemetrie. Cette question est le seul instrument
    qui regarde ce point aveugle."""
    item = next(i for i in PAR_CAS.items if "erreur introduite" in i.libelle)
    assert item.obligatoire


def test_la_charge_de_correction_n_est_plus_demandee():
    """La distance d'edition entre texte propose et texte valide la mesure
    objectivement. Redemander ce que la donnee sait deja coute du temps a des
    questions que rien ne remplace."""
    assert not any("beaucoup de corrections" in i.libelle for i in PAR_CAS.items)


def test_la_preference_avec_ou_sans_est_demandee():
    """C'est l'item qui porte la conclusion de l'etude, sous la seule forme que
    le praticien reconnaitrait comme la sienne."""
    item = next(i for i in PAR_CAS.items if "prefere rediger" in i.libelle)
    assert set(item.options) == {
        "Avec le logiciel", "Sans le logiciel", "Indifferent"
    }
    assert item.obligatoire


def test_le_questionnaire_par_cas_reste_court():
    """Une minute annoncee : au-dela, le praticien repond n'importe quoi ou
    abandonne l'etude. Deux items sont conditionnels et ne s'affichent que sur
    une reponse positive, donc le cas courant est plus court que ce compte."""
    assert PAR_CAS.duree_estimee_s <= 60
    assert len(PAR_CAS.items) <= 12
    conditionnels = sum(1 for i in PAR_CAS.items if i.depend_de)
    assert len(PAR_CAS.items) - conditionnels <= 10


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
    """Ce sont des AFFIRMATIONS : 'le logiciel a facilite la redaction'.
    L'accord est la bonne echelle pour celles-la."""
    for item in PAR_CAS.items:
        if item.type == "likert_5":
            assert "accord" in item.ancre_basse.lower(), item.id


def test_un_item_formule_en_question_n_est_pas_cote_en_accord():
    """'Faites-vous confiance a ... ?' n'appelle pas 'tout a fait d'accord'."""
    item = next(i for i in CATALOGUE["inclusion"].items if i.id == "inclusion_14")
    assert "accord" not in item.ancre_basse.lower()


# --- La cadence du F-SUS ----------------------------------------------------


def test_le_fsus_est_periodique_et_pas_par_cas():
    """Il mesure l'utilisabilite d'un SYSTEME apres usage, pas une tache. Le
    poser apres chaque cas produirait des reponses qui ne se somment pas en un
    score valide, et ferait decrocher le praticien."""
    assert all(i.id.startswith("fsus_") for i in CATALOGUE["periodique"].items)
    assert not any(i.id.startswith("fsus_") for i in PAR_CAS.items)


def test_le_fsus_ne_figure_plus_en_fin_d_etude():
    """Le dernier releve periodique EST la mesure finale : le redemander ferait
    un doublon a quelques jours d'intervalle."""
    assert not any(i.id.startswith("fsus_") for i in CATALOGUE["fin_etude"].items)


def test_la_cadence_est_comptee_a_partir_des_cas_clos():
    """Un decompte tenu par le client deriverait d'un poste a l'autre, et la
    courbe ne serait plus alignee entre praticiens."""
    assert not periodique_du(0)
    assert [n for n in range(1, 16) if periodique_du(n)] == [5, 10, 15]
