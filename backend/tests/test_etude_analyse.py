"""Calcul des indicateurs de l'etude.

Ces tests sont la relecture par les pairs, ecrite d'avance. Chacun defend un
denominateur : c'est la que se joue la difference entre un resultat publiable
et un taux flatteur.
"""

from datetime import UTC, datetime, timedelta

from etude.analyse import (
    ITEM_ATTESTATION,
    ITEM_COMPREHENSION,
    ITEM_ERREUR_INTRODUITE,
    ITEM_OMISSION,
    ITEM_OUBLI_RATTRAPE,
    ITEM_PREFERENCE,
    ITEM_SOUHAIT_DE_CONTINUER,
    DecisionObservee,
    DossierObserve,
    ReponseObservee,
    Taux,
    agreger_dossiers,
    agreger_oui_non,
    agreger_fsus,
    agreger_par_cas,
    calculer_indicateurs,
    calculer_temps,
    compter_praticiens_favorables,
    decouper_releves_fsus,
    depouiller,
    ecart_type,
    mediane,
    moyenne,
    resumer,
    retenir_reponses,
    synthetiser,
    terciles,
)
from etude.questionnaires import CATALOGUE
from etude.vocabulaire import (
    QUESTIONNAIRE_FIN_ETUDE,
    QUESTIONNAIRE_PAR_CAS,
    QUESTIONNAIRE_PERIODIQUE,
    TYPE_CODE,
    TYPE_COMPLETUDE,
    TYPE_RESTITUTION,
)

DEBUT = datetime(2026, 9, 1, 9, 0, tzinfo=UTC)


def _restitution(decision, hative=False, change=False, nature=None, ancree=True):
    return DecisionObservee(
        TYPE_RESTITUTION, decision, hative, None, change, nature, ancree
    )


def _code(decision):
    return DecisionObservee(TYPE_CODE, decision)


def _completude(decision):
    return DecisionObservee(TYPE_COMPLETUDE, decision)


def _par_cas(item, valeur, dossier="d1", praticien="p1"):
    """Une reponse a un item du questionnaire par cas."""
    return ReponseObservee(
        praticien_id=praticien,
        questionnaire=QUESTIONNAIRE_PAR_CAS,
        item=item,
        valeur=valeur,
        dossier_id=dossier,
        repondu_a=DEBUT,
    )


def _releve_fsus(praticien, cotations, moment):
    """Les dix items d'un passage du F-SUS, cotes dans l'ordre."""
    return [
        ReponseObservee(
            praticien_id=praticien,
            questionnaire=QUESTIONNAIRE_PERIODIQUE,
            item=f"fsus_{rang:02d}",
            valeur=str(cotation),
            repondu_a=moment,
        )
        for rang, cotation in enumerate(cotations, start=1)
    ]


#: Cotations alternees qui produisent les scores de reference du SUS. Un item
#: impair cote 5 vaut 4 points, un item pair cote 1 en vaut 4 : dix fois quatre,
#: multiplies par 2,5, font 100.
_FSUS_100 = [5, 1] * 5
_FSUS_75 = [4, 2] * 5
_FSUS_50 = [3] * 10


def _option(questionnaire, item, rang):
    """Le libelle exact d'une option, lu dans le catalogue et non recopie."""
    for declare in CATALOGUE[questionnaire].items:
        if declare.id == item:
            return declare.options[rang]
    raise AssertionError(f"item inconnu au catalogue : {item}")


# --- La regle du denominateur nul -------------------------------------------


def test_un_denominateur_nul_donne_none_pas_zero():
    """Ecrire 0 % la ou l'on n'a rien observe est la maniere la plus courante
    de mentir avec un tableau."""
    assert Taux(0, 0).valeur is None
    assert Taux(0, 5).valeur == 0.0


def test_chaque_taux_expose_ses_deux_termes():
    """Un lecteur doit pouvoir refaire le calcul : un taux sans son
    denominateur n'est pas un resultat."""
    indicateurs = calculer_indicateurs([_restitution("conforme")])
    publie = indicateurs.en_dict()["taux"]["acceptation_sans_modification"]
    assert publie["numerateur"] == 1
    assert publie["denominateur"] == 1
    assert publie["valeur"] == 1.0


# --- Le point le plus sensible : l'exactitude des codes ---------------------


def test_je_ne_sais_pas_sort_des_deux_termes():
    """La compter comme un echec punirait l'honnetete ; la compter comme une
    reussite mesurerait de l'acquiescement."""
    indicateurs = calculer_indicateurs(
        [_code("juste"), _code("corrige"), _code("je_ne_sais_pas")]
    )
    assert indicateurs.exactitude_codes.numerateur == 1
    assert indicateurs.exactitude_codes.denominateur == 2
    assert indicateurs.exactitude_codes.valeur == 0.5


def test_l_abstention_est_mesuree_a_part():
    """Un taux d'abstention eleve est lui-meme un resultat sur la lisibilite
    des codes proposes : il ne doit pas disparaitre du depouillement."""
    indicateurs = calculer_indicateurs(
        [_code("juste"), _code("je_ne_sais_pas"), _code("je_ne_sais_pas")]
    )
    assert indicateurs.abstention_codes.numerateur == 2
    assert indicateurs.abstention_codes.denominateur == 3


def test_un_code_est_juste_ou_corrige_pas_conforme():
    """Les grilles sont distinctes : 'conforme' appartient a la restitution et
    ne doit rien alimenter du cote code."""
    indicateurs = calculer_indicateurs([_code("juste"), _restitution("conforme")])
    assert indicateurs.exactitude_codes.denominateur == 1
    assert indicateurs.acceptation_sans_modification.denominateur == 1


# --- Hallucination et bruit -------------------------------------------------


def test_le_taux_d_hallucination_ne_compte_que_les_restitutions():
    """'non_dicte' mesure une affirmation non prononcee. Melanger les
    completudes au denominateur diluerait mecaniquement le taux."""
    decisions = [
        _restitution("non_dicte"),
        _restitution("conforme"),
        _completude("non_pertinent"),
        _completude("non_pertinent"),
        _completude("non_pertinent"),
    ]
    indicateurs = calculer_indicateurs(decisions)
    assert indicateurs.hallucination.denominateur == 2
    assert indicateurs.hallucination.valeur == 0.5


def test_le_bruit_est_distinct_de_l_hallucination():
    """Une proposition juste mais hors sujet n'est pas une hallucination :
    confondre les deux surestimerait le danger clinique."""
    indicateurs = calculer_indicateurs(
        [_restitution("hors_sujet"), _restitution("non_dicte")]
    )
    assert indicateurs.bruit.numerateur == 1
    assert indicateurs.hallucination.numerateur == 1


# --- Completude -------------------------------------------------------------


def test_pertinent_non_retenu_compte_comme_une_reussite():
    """Un praticien qui juge la suggestion pertinente et choisit souverainement
    de ne pas l'ecrire valide le systeme. Le compter comme un echec confondrait
    la qualite de la suggestion avec la decision editoriale."""
    indicateurs = calculer_indicateurs(
        [_completude("pertinent_ajoute"),
         _completude("pertinent_non_retenu"),
         _completude("non_pertinent")]
    )
    assert indicateurs.utilite_completude.numerateur == 2
    assert indicateurs.utilite_completude.denominateur == 3


# --- Les decisions hatives --------------------------------------------------


def test_les_hatives_sont_isolees_pas_supprimees():
    """Le verrou d'export cree une pression a cliquer vite. L'ecart entre les
    deux lectures mesure combien il a gonfle les resultats."""
    decisions = [
        _restitution("conforme", hative=True),
        _restitution("conforme", hative=True),
        _restitution("non_dicte"),
    ]
    resultat = depouiller(decisions)
    assert resultat.toutes.acceptation_sans_modification.valeur is not None
    assert resultat.toutes.acceptation_sans_modification.valeur > 0.6
    # Hors hatives il ne reste qu'une hallucination : le taux s'effondre.
    assert resultat.hors_hatives.acceptation_sans_modification.valeur == 0.0
    assert resultat.hors_hatives.decidees == 1


def test_le_taux_de_hatives_est_publie():
    indicateurs = calculer_indicateurs(
        [_restitution("conforme", hative=True), _restitution("conforme")]
    )
    assert indicateurs.decisions_hatives.valeur == 0.5


# --- Explicabilite ----------------------------------------------------------


def test_le_changement_apres_justification_est_un_indicateur():
    """C'est LA mesure d'explicabilite : la justification sert-elle a quelque
    chose, ou n'est-elle qu'un ornement ?"""
    indicateurs = calculer_indicateurs(
        [_restitution("corrige", change=True), _restitution("conforme")]
    )
    assert indicateurs.changement_apres_justification.valeur == 0.5


def test_les_propositions_non_decidees_sont_comptees_a_part():
    """Elles ne doivent alimenter aucun taux, mais leur nombre dit si le
    praticien est alle au bout."""
    indicateurs = calculer_indicateurs([_restitution("conforme"), _restitution(None)])
    assert indicateurs.decidees == 1
    assert indicateurs.non_decidees == 1
    assert indicateurs.acceptation_sans_modification.denominateur == 1


def test_aucune_decision_ne_produit_aucun_taux():
    indicateurs = calculer_indicateurs([])
    assert indicateurs.acceptation_sans_modification.valeur is None
    assert indicateurs.exactitude_codes.valeur is None


# --- Temps ------------------------------------------------------------------


class _DossierFactice:
    def __init__(self, base):
        self.t0_debut_dictee = base
        self.t1_fin_dictee = base + timedelta(seconds=60)
        self.t2_affichage = base + timedelta(seconds=75)
        self.t5_cloture = base + timedelta(seconds=375)


def test_les_pauses_sont_deduites_du_temps_de_revision():
    """Les interruptions sont la norme en conditions reelles : les laisser
    dans le chronometre mesurerait le service, pas l'outil."""
    dossier = _DossierFactice(datetime(2026, 9, 1, 9, 0, tzinfo=UTC))
    temps = calculer_temps(dossier, pauses_ms=120_000, nb_pauses=2)
    assert temps.revision_ms == 300_000
    assert temps.revision_nette_ms == 180_000
    assert temps.nb_pauses == 2


def test_un_horodatage_manquant_ne_fabrique_pas_une_duree():
    dossier = _DossierFactice(datetime(2026, 9, 1, 9, 0, tzinfo=UTC))
    dossier.t5_cloture = None
    temps = calculer_temps(dossier, pauses_ms=0, nb_pauses=0)
    assert temps.revision_ms is None
    assert temps.revision_nette_ms is None


def test_des_pauses_plus_longues_que_la_revision_ne_donnent_pas_un_negatif():
    dossier = _DossierFactice(datetime(2026, 9, 1, 9, 0, tzinfo=UTC))
    temps = calculer_temps(dossier, pauses_ms=999_000, nb_pauses=1)
    assert temps.revision_nette_ms == 0


# --- Effet d'apprentissage --------------------------------------------------


def test_les_terciles_separent_le_debut_de_la_fin():
    """Sans ce decoupage, l'effet d'apprentissage se confondrait avec une
    performance de l'outil."""
    debut, milieu, fin = terciles([9.0, 8.0, 7.0, 6.0, 5.0, 4.0])
    assert len(debut) == len(milieu) == len(fin) == 2
    assert moyenne(debut) > moyenne(fin)


def test_les_terciles_tolerent_une_serie_courte():
    assert terciles([]) == [[], [], []]
    assert terciles([1.0]) == [[], [], [1.0]]


def test_la_moyenne_d_une_serie_vide_est_none():
    """Jamais zero : une absence de mesure n'est pas une mesure a zero."""
    assert moyenne([]) is None


# --- Statistique descriptive -------------------------------------------------


def test_la_mediane_resiste_a_une_interruption_longue():
    """Mediane et pas moyenne sur une duree : une seule interruption ecrase une
    moyenne et ferait conclure a une lenteur que personne n'a vecue."""
    durees = [100.0, 110.0, 120.0, 130.0, 9000.0]
    assert mediane(durees) == 120.0
    assert moyenne(durees) > 1800


def test_l_ecart_type_d_une_mesure_unique_est_none():
    """En publier zero laisserait croire a une unanimite qu'on n'a pas
    observee."""
    assert ecart_type([70.0]) is None
    assert ecart_type([]) is None
    assert ecart_type([70.0, 80.0]) is not None


def test_une_distribution_vide_ne_fabrique_pas_d_intervalle():
    vide = resumer([])
    assert vide.effectif == 0
    assert vide.mediane is None
    assert vide.minimum is None and vide.maximum is None


def test_une_distribution_publie_son_intervalle():
    """Dix minutes entre neuf et onze et dix minutes entre deux et quarante ne
    decrivent pas le meme outil."""
    resume = resumer([2.0, 10.0, 40.0])
    assert (resume.mediane, resume.minimum, resume.maximum) == (10.0, 2.0, 40.0)
    assert resume.effectif == 3


# --- Le score F-SUS ----------------------------------------------------------


def test_les_releves_successifs_d_un_praticien_sont_distingues():
    """Le F-SUS revient tous les cinq comptes rendus : confondre deux passages
    en un seul ecraserait la courbe, qui est tout l'interet de le repeter."""
    reponses = [
        *_releve_fsus("p1", _FSUS_50, DEBUT),
        *_releve_fsus("p1", _FSUS_100, DEBUT + timedelta(days=7)),
    ]
    releves = decouper_releves_fsus(reponses)
    assert [(r.rang, r.score) for r in releves] == [(1, 50.0), (2, 100.0)]


def test_la_courbe_distingue_l_apprentissage_de_la_lassitude():
    """Une moyenne unique confond un outil qu'on apprend a aimer avec un outil
    dont on se lasse ; une courbe, non."""
    reponses = [
        *_releve_fsus("p1", _FSUS_50, DEBUT),
        *_releve_fsus("p1", _FSUS_100, DEBUT + timedelta(days=7)),
        *_releve_fsus("p2", _FSUS_50, DEBUT),
        *_releve_fsus("p2", _FSUS_100, DEBUT + timedelta(days=7)),
    ]
    courbe = agreger_fsus(reponses).courbe
    assert [point.moyenne for point in courbe] == [50.0, 100.0]
    assert [point.effectif for point in courbe] == [2, 2]


def test_deux_releves_du_meme_horodatage_restent_deux_releves_complets():
    """Une base qui n'horodate qu'a la seconde peut dater deux releves de la
    MEME seconde. Decouper la-dessus transformait deux F-SUS complets en une
    dizaine de fragments incotables — soit la destruction silencieuse d'un
    critere PRINCIPAL."""
    reponses = [
        *_releve_fsus("p1", _FSUS_100, DEBUT),
        *_releve_fsus("p1", _FSUS_75, DEBUT),
    ]
    releves = decouper_releves_fsus(reponses)
    assert len(releves) == 2
    assert sorted(r.score for r in releves) == [75.0, 100.0]


def test_un_releve_coupe_par_l_horloge_reste_un_seul_releve():
    """L'horloge peut tourner au milieu de l'insertion des dix items : les
    separer en deux releves rendrait les deux incotables."""
    reponses = _releve_fsus("p1", _FSUS_100, DEBUT)
    for tardive in reponses[6:]:
        tardive.repondu_a = DEBUT + timedelta(seconds=1)
    releves = decouper_releves_fsus(reponses)
    assert len(releves) == 1
    assert releves[0].score == 100.0


def test_un_fsus_incalculable_n_entre_dans_aucune_moyenne():
    """Un item manquant rend le score incalculable : mieux vaut None qu'un
    score partiel qu'on prendrait pour un score complet."""
    incomplet = _releve_fsus("p1", _FSUS_100, DEBUT)[:9]
    reponses = [*incomplet, *_releve_fsus("p2", _FSUS_75, DEBUT)]
    agregat = agreger_fsus(reponses)
    assert agregat.ensemble.moyenne == 75.0
    assert agregat.ensemble.effectif == 1
    # Le releve rendu mais incotable ne disparait pas du tableau.
    assert agregat.ensemble.non_cotables == 1


def test_un_fsus_hors_echelle_ne_se_cote_pas():
    """Une valeur qui n'est pas une cotation ne se remplace pas par un zero :
    elle rend le score incalculable, et cela se voit."""
    reponses = _releve_fsus("p1", _FSUS_100, DEBUT)
    reponses[3].valeur = "je ne sais pas"
    agregat = agreger_fsus(reponses)
    assert agregat.ensemble.moyenne is None
    assert agregat.ensemble.non_cotables == 1


def test_chaque_praticien_porte_son_propre_effectif_de_releves():
    """Un F-SUS moyen sur deux releves n'a pas le poids d'un F-SUS moyen sur
    quarante, et le tableau doit le dire."""
    reponses = [
        *_releve_fsus("p1", _FSUS_50, DEBUT),
        *_releve_fsus("p1", _FSUS_100, DEBUT + timedelta(days=7)),
        *_releve_fsus("p2", _FSUS_75, DEBUT),
    ]
    agregat = agreger_fsus(reponses)
    assert agregat.par_praticien["p1"].effectif == 2
    assert agregat.par_praticien["p1"].moyenne == 75.0
    assert agregat.par_praticien["p2"].effectif == 1
    # A une seule mesure, l'ecart-type n'existe pas.
    assert agregat.par_praticien["p2"].ecart_type is None
    assert agregat.courbe_par_praticien["p1"] == [50.0, 100.0]


def test_un_fsus_absent_ne_fabrique_pas_un_score():
    agregat = agreger_fsus([])
    assert agregat.ensemble.moyenne is None
    assert agregat.ensemble.effectif == 0
    assert agregat.courbe == []


# --- Les items declares apres chaque cas -------------------------------------


def test_le_taux_d_omission_porte_son_denominateur():
    """C'est la seule mesure que la telemetrie ne peut pas produire : un oubli
    ne laisse aucune trace."""
    reponses = [
        _par_cas(ITEM_OMISSION, "Oui", dossier="d1"),
        _par_cas(ITEM_OMISSION, "Non", dossier="d2"),
        _par_cas(ITEM_OMISSION, "Non", dossier="d3"),
    ]
    omission = agreger_par_cas(reponses).omission
    assert (omission.numerateur, omission.denominateur) == (1, 3)


def test_une_reponse_ni_oui_ni_non_sort_des_deux_termes():
    """La compter comme un non fabriquerait une securite qu'on n'a pas
    mesuree."""
    reponses = [
        _par_cas(ITEM_OMISSION, "Oui", dossier="d1"),
        _par_cas(ITEM_OMISSION, "", dossier="d2"),
    ]
    omission = agreger_par_cas(reponses).omission
    assert (omission.numerateur, omission.denominateur) == (1, 1)


def test_l_omission_non_mesuree_vaut_none_pas_zero():
    assert agreger_par_cas([]).omission.valeur is None


def test_l_attestation_et_l_erreur_introduite_sont_mesurees_a_part():
    """Sans l'attestation on ignore si le praticien SIGNERAIT ces comptes
    rendus ; sans l'erreur introduite on ne regarde pas le point aveugle."""
    reponses = [
        _par_cas(ITEM_ATTESTATION, "Oui", dossier="d1"),
        _par_cas(ITEM_ATTESTATION, "Non", dossier="d2"),
        _par_cas(ITEM_ERREUR_INTRODUITE, "Oui", dossier="d1"),
        _par_cas(ITEM_ERREUR_INTRODUITE, "Non", dossier="d2"),
    ]
    agregat = agreger_par_cas(reponses)
    assert agregat.attestation.valeur == 0.5
    assert agregat.erreur_introduite.valeur == 0.5


def test_la_comprehension_se_moyenne_sur_l_echelle():
    """Aucune telemetrie ne dit si le praticien a COMPRIS, seulement s'il a
    ouvert un panneau : cet item n'a pas de substitut."""
    reponses = [
        _par_cas(ITEM_COMPREHENSION, "4", dossier="d1"),
        _par_cas(ITEM_COMPREHENSION, "5", dossier="d2"),
    ]
    comprehension = agreger_par_cas(reponses).comprehension
    assert comprehension.moyenne == 4.5
    assert comprehension.effectif == 2


def test_une_reponse_hors_echelle_sort_de_la_moyenne_mais_reste_comptee():
    """La coter a zero ecraserait la moyenne d'un item ou l'option existe
    justement pour ne pas repondre."""
    reponses = [
        _par_cas(ITEM_COMPREHENSION, "4", dossier="d1"),
        _par_cas(ITEM_COMPREHENSION, "Non applicable", dossier="d2"),
    ]
    comprehension = agreger_par_cas(reponses).comprehension
    assert comprehension.moyenne == 4.0
    assert comprehension.effectif == 1
    assert comprehension.non_cotables == 1


def test_les_deux_oui_de_l_oubli_rattrape_ne_s_additionnent_jamais():
    """« Je l'aurais omis » est une affirmation de SECURITE ; « je l'aurais
    ecrit de toute facon » n'est qu'un confort. Les confondre gonflerait toute
    la couche de completude."""
    omis = _option(QUESTIONNAIRE_PAR_CAS, ITEM_OUBLI_RATTRAPE, 0)
    de_toute_facon = _option(QUESTIONNAIRE_PAR_CAS, ITEM_OUBLI_RATTRAPE, 1)
    reponses = [
        _par_cas(ITEM_OUBLI_RATTRAPE, omis, dossier="d1"),
        _par_cas(ITEM_OUBLI_RATTRAPE, de_toute_facon, dossier="d2"),
        _par_cas(ITEM_OUBLI_RATTRAPE, de_toute_facon, dossier="d3"),
        _par_cas(ITEM_OUBLI_RATTRAPE, "Non", dossier="d4"),
    ]
    repartition = agreger_par_cas(reponses).oubli_rattrape
    assert repartition.options[omis].numerateur == 1
    assert repartition.options[de_toute_facon].numerateur == 2
    assert repartition.options[omis].denominateur == 4
    # Chaque option reste une ligne : rien dans la structure ne permet de les
    # additionner par inadvertance.
    assert len(repartition.options) == 3


def test_une_reponse_hors_catalogue_est_comptee_a_part():
    """Un libelle qui ne figure plus au catalogue ne doit pas disparaitre du
    denominateur sans que rien ne le signale."""
    reponses = [
        _par_cas(ITEM_PREFERENCE, "Avec le tres vieux logiciel", dossier="d1"),
        _par_cas(
            ITEM_PREFERENCE,
            _option(QUESTIONNAIRE_PAR_CAS, ITEM_PREFERENCE, 0),
            dossier="d2",
        ),
    ]
    repartition = agreger_par_cas(reponses).preference
    assert repartition.effectif == 1
    assert repartition.hors_options == 1


def test_la_preference_porte_les_trois_options_du_catalogue():
    """L'item qui porte la conclusion de l'etude sous la seule forme que le
    praticien reconnaitrait comme la sienne."""
    avec = _option(QUESTIONNAIRE_PAR_CAS, ITEM_PREFERENCE, 0)
    sans = _option(QUESTIONNAIRE_PAR_CAS, ITEM_PREFERENCE, 1)
    reponses = [
        _par_cas(ITEM_PREFERENCE, avec, dossier="d1"),
        _par_cas(ITEM_PREFERENCE, sans, dossier="d2"),
    ]
    repartition = agreger_par_cas(reponses).preference
    assert repartition.options[avec].valeur == 0.5
    assert repartition.options[sans].valeur == 0.5
    assert set(repartition.options) == {
        _option(QUESTIONNAIRE_PAR_CAS, ITEM_PREFERENCE, rang) for rang in range(3)
    }


def test_un_praticien_ne_pese_qu_une_voix_sur_le_souhait_de_continuer():
    """Le questionnaire de fin d'etude peut etre renvoye : compter deux fois le
    meme praticien lui donnerait deux voix sur un critere qui se lit en
    praticiens."""
    reponses = [
        ReponseObservee("p1", QUESTIONNAIRE_FIN_ETUDE, ITEM_SOUHAIT_DE_CONTINUER,
                        "Non", None, DEBUT),
        ReponseObservee("p1", QUESTIONNAIRE_FIN_ETUDE, ITEM_SOUHAIT_DE_CONTINUER,
                        "Oui", None, DEBUT + timedelta(days=1)),
        ReponseObservee("p2", QUESTIONNAIRE_FIN_ETUDE, ITEM_SOUHAIT_DE_CONTINUER,
                        "Peut-etre", None, DEBUT),
    ]
    favorables = compter_praticiens_favorables(reponses)
    assert (favorables.numerateur, favorables.denominateur) == (1, 2)


# --- L'exclusion des dossiers ecartes ----------------------------------------


def test_une_reponse_d_un_dossier_exclu_n_entre_dans_aucun_calcul():
    """Une exclusion qui n'exclut pas le questionnaire du meme cas laisserait un
    essai peser sur un critere de securite."""
    reponses = [
        _par_cas(ITEM_OMISSION, "Oui", dossier="essai"),
        _par_cas(ITEM_OMISSION, "Non", dossier="vrai"),
    ]
    retenues = retenir_reponses(reponses, {"vrai"})
    omission = agreger_par_cas(retenues).omission
    assert (omission.numerateur, omission.denominateur) == (0, 1)


def test_un_releve_sans_dossier_survit_a_l_exclusion_d_un_cas():
    """Ecarter un cas d'essai ne doit pas effacer le F-SUS de celui qui l'a
    ouvert : le releve porte sur le praticien, pas sur un cas."""
    reponses = _releve_fsus("p1", _FSUS_100, DEBUT)
    assert len(retenir_reponses(reponses, set())) == 10


# --- La nature des corrections -----------------------------------------------


def test_une_reformulation_de_style_n_est_pas_une_erreur_du_systeme():
    """C'est le chiffre le plus important du lot : sans lui, une reformulation
    de confort et une erreur clinique comptent pareil."""
    decisions = [
        _restitution("corrige", nature="style"),
        _restitution("corrige", nature="style"),
        _restitution("corrige", nature="erreur_fond"),
        _restitution("corrige", nature="precision"),
    ]
    corrections = calculer_indicateurs(decisions).corrections
    assert corrections.corrigees == 4
    assert corrections.style.valeur == 0.5
    assert corrections.erreur_fond.valeur == 0.25
    assert corrections.precision.valeur == 0.25


def test_une_correction_sans_nature_declaree_n_impute_rien_a_personne():
    """On ne fabrique pas une erreur a partir d'une absence de reponse, et trois
    natures qui ne somment pas a cent pour cent doivent s'expliquer."""
    decisions = [
        _restitution("corrige", nature="erreur_fond"),
        _restitution("corrige", nature=None),
    ]
    corrections = calculer_indicateurs(decisions).corrections
    assert corrections.erreur_fond.valeur == 0.5
    assert corrections.non_declaree.numerateur == 1
    assert corrections.non_declaree.denominateur == 2


def test_la_justesse_sur_le_fond_ajoute_le_style_au_conforme():
    """Le systeme avait raison sur le fond : valide tel quel, ou reecrit pour la
    seule forme."""
    decisions = [
        _restitution("conforme"),
        _restitution("corrige", nature="style"),
        _restitution("corrige", nature="erreur_fond"),
        _restitution("non_dicte"),
    ]
    corrections = calculer_indicateurs(decisions).corrections
    assert corrections.justesse_sur_le_fond.numerateur == 2
    assert corrections.justesse_sur_le_fond.denominateur == 4


def test_une_correction_de_precision_ne_compte_pas_comme_une_justesse():
    """Le fond etait juste mais INCOMPLET : compter un succes partiel comme une
    justesse gonflerait le seul chiffre qui doive rester dur."""
    decisions = [_restitution("conforme"), _restitution("corrige", nature="precision")]
    corrections = calculer_indicateurs(decisions).corrections
    assert corrections.justesse_sur_le_fond.numerateur == 1


def test_sans_correction_la_repartition_des_natures_reste_vide():
    corrections = calculer_indicateurs([_restitution("conforme")]).corrections
    assert corrections.style.valeur is None
    assert corrections.erreur_fond.valeur is None


# --- Le critere bloquant : accepter une assertion que rien ne soutient -------


def test_une_assertion_non_ancree_acceptee_est_comptee_a_part():
    """Une assertion que rien dans la dictee ne soutient, et que le praticien a
    pourtant validee telle quelle : c'est le critere bloquant du protocole."""
    decisions = [
        _restitution("conforme", ancree=False),
        _restitution("non_dicte", ancree=False),
        _restitution("conforme"),
    ]
    indicateurs = calculer_indicateurs(decisions)
    assert indicateurs.acceptation_non_ancree.numerateur == 1
    # Le denominateur est celui des seules assertions non ancrees : le rapporter
    # au corpus entier diluerait le signal jusqu'a l'effacer.
    assert indicateurs.acceptation_non_ancree.denominateur == 2


# --- Les temps agreges -------------------------------------------------------


def _dossier(praticien, index, revision, justif=False, session="s1"):
    return DossierObserve(praticien, session, index, revision, justif)


def test_les_temps_sont_resumes_par_praticien():
    dossiers = [
        _dossier("p1", 0, 100),
        _dossier("p1", 1, 300),
        _dossier("p2", 0, 5000),
    ]
    agregat = agreger_dossiers(dossiers)
    assert agregat.revision_nette_par_praticien["p1"].mediane == 200.0
    assert agregat.revision_nette_par_praticien["p1"].effectif == 2
    assert agregat.revision_nette_par_praticien["p2"].mediane == 5000.0


def test_les_terciles_se_decoupent_praticien_par_praticien():
    """Des terciles calcules sur le corpus entier melangeraient les premiers cas
    d'un praticien avec les derniers d'un autre : ils ne mesureraient plus
    l'apprentissage mais l'ordre d'arrivee des participants."""
    dossiers = [
        *(_dossier("p1", index, temps)
          for index, temps in enumerate([900, 800, 700, 600, 500, 400])),
        *(_dossier("p2", index, temps)
          for index, temps in enumerate([90, 80, 70, 60, 50, 40])),
    ]
    debut, milieu, fin = agreger_dossiers(dossiers).revision_nette_par_tercile
    assert debut.effectif == milieu.effectif == fin.effectif == 4
    # Le premier tercile contient les deux premiers cas de CHAQUE praticien.
    assert debut.minimum == 80.0 and debut.maximum == 900.0
    assert fin.maximum == 500.0


def test_un_dossier_sans_horodatage_sort_de_la_serie_au_lieu_d_y_entrer_a_zero():
    dossiers = [_dossier("p1", 0, None), _dossier("p1", 1, 400)]
    agregat = agreger_dossiers(dossiers)
    assert agregat.revision_nette.effectif == 1
    assert agregat.revision_nette.mediane == 400.0


def test_la_consultation_des_justifications_se_compte_par_cas():
    dossiers = [
        _dossier("p1", 0, 100, justif=True),
        _dossier("p1", 1, 100, justif=False),
    ]
    consultation = agreger_dossiers(dossiers).consultation_justifications
    assert (consultation.numerateur, consultation.denominateur) == (1, 2)


def test_sans_dossier_aucun_temps_n_est_fabrique():
    agregat = agreger_dossiers([])
    assert agregat.revision_nette.mediane is None
    assert agregat.consultation_justifications.valeur is None


# --- Le tableau de couverture ------------------------------------------------


def _couverture(**kwargs):
    """Le tableau de couverture, indexe par cle de critere."""
    synthese = synthetiser(
        decisions=kwargs.get("decisions", []),
        reponses=kwargs.get("reponses", []),
        dossiers=kwargs.get("dossiers", []),
    )
    return {critere.cle: critere for critere in synthese.couverture}


def test_chaque_critere_principal_du_protocole_est_couvert():
    """C'est ce que le proprietaire regarde en premier, et c'est ce qui lui dit
    ou en est l'etude."""
    couverture = _couverture()
    principaux = {
        cle for cle, critere in couverture.items() if critere.rang == "principal"
    }
    assert principaux == {
        "propositions_non_soutenues",
        "non_soutenues_acceptees",
        "omissions_signalees",
        "acceptation_sans_modification",
        "score_fsus",
        "praticiens_souhaitant_continuer",
    }


def test_chaque_critere_porte_son_effectif_et_son_seuil():
    for critere in _couverture().values():
        publie = critere.en_dict()
        assert "effectif" in publie
        assert "effectif_minimal" in publie
        assert "donnees_suffisantes" in publie


def test_atteindre_un_seuil_et_pouvoir_conclure_sont_deux_questions():
    """Une valeur peut etre du bon cote du seuil sur deux observations : le
    tableau doit dire les deux, parce que les deux sont vrais."""
    decisions = [_restitution("conforme"), _restitution("conforme")]
    critere = _couverture(decisions=decisions)["acceptation_sans_modification"]
    assert critere.valeur == 1.0
    assert critere.atteint is True
    assert critere.donnees_suffisantes is False


def test_un_critere_sans_mesure_ne_conclut_ni_dans_un_sens_ni_dans_l_autre():
    """Ecrire 0 % la ou l'on n'a rien observe est la maniere la plus courante de
    mentir avec un tableau."""
    critere = _couverture()["omissions_signalees"]
    assert critere.valeur is None
    assert critere.atteint is None
    assert critere.donnees_suffisantes is False


def test_un_critere_descriptif_ne_se_declare_jamais_atteint():
    """Le protocole ne fixe aucun seuil de temps absolu : en inventer un serait
    fixer un seuil apres avoir vu les donnees."""
    dossiers = [_dossier("p1", 0, 1000)]
    critere = _couverture(dossiers=dossiers)["temps_revision_net"]
    assert critere.seuil is None
    assert critere.atteint is None
    assert critere.valeur == 1000.0


def test_le_taux_de_soumission_du_college_est_declare_non_depouillable():
    """Rien ne conserve la trace d'arbitrage en base. Le reconstruire depuis le
    compte rendu donnerait un chiffre faux, puisque les assertions AFFIRMEES ne
    sont volontairement pas enregistrees."""
    critere = _couverture()["taux_de_soumission_college"]
    assert critere.valeur is None
    assert critere.donnees_suffisantes is False
    assert "NON DEPOUILLABLE" in critere.note


def test_le_fsus_de_la_couverture_compte_des_releves_pas_des_praticiens():
    reponses = [
        *_releve_fsus("p1", _FSUS_100, DEBUT),
        *_releve_fsus("p1", _FSUS_50, DEBUT + timedelta(days=7)),
    ]
    critere = _couverture(reponses=reponses)["score_fsus"]
    assert critere.valeur == 75.0
    assert critere.effectif == 2


def test_la_couverture_vient_en_tete_de_la_synthese():
    """Elle dit ou en est l'etude avant de dire ce qu'elle trouve, et c'est dans
    cet ordre qu'un tableau se lit."""
    publie = synthetiser([], [], []).en_dict()
    assert next(iter(publie)) == "couverture"
    assert set(publie) == {
        "couverture",
        "propositions",
        "fsus",
        "par_cas",
        "dossiers",
        "praticiens_favorables",
    }


# --- Les faux signaux trouves par la verification adversariale --------------


def test_un_questionnaire_renvoye_deux_fois_ne_double_pas_le_denominateur():
    """Le taux d'omission est un critere PRINCIPAL de securite. Compter les
    LIGNES au lieu des COMPTES RENDUS le faussait : deux CR questionnes dont un
    avec omission donnaient 2/3 au lieu de 1/2. Rien n'empeche un double-clic
    ni une reprise apres coupure."""
    reponses = [
        _par_cas(ITEM_OMISSION, "Oui", dossier="d1"),
        _par_cas(ITEM_OMISSION, "Oui", dossier="d1"),
        _par_cas(ITEM_OMISSION, "Non", dossier="d2"),
    ]
    taux = agreger_oui_non(
        reponses, QUESTIONNAIRE_PAR_CAS, ITEM_OMISSION, "Omissions"
    )
    assert (taux.numerateur, taux.denominateur) == (1, 2)


def test_une_reprise_ecrase_la_reponse_precedente():
    """Si le praticien se reprend, c'est sa reprise qui vaut."""
    tardive = ReponseObservee(
        praticien_id="p1",
        questionnaire=QUESTIONNAIRE_PAR_CAS,
        item=ITEM_OMISSION,
        valeur="Non",
        dossier_id="d1",
        repondu_a=DEBUT + timedelta(seconds=30),
    )
    taux = agreger_oui_non(
        [_par_cas(ITEM_OMISSION, "Oui", dossier="d1"), tardive],
        QUESTIONNAIRE_PAR_CAS,
        ITEM_OMISSION,
        "Omissions",
    )
    assert (taux.numerateur, taux.denominateur) == (0, 1)


def test_un_numerateur_inobservable_ne_se_publie_pas():
    """Le pire des faux signaux : un zero confiant sur une question que
    personne n'a posee. Tant qu'aucune nature de correction n'est declaree, le
    taux d'erreurs de fond vaut zero parce que la question n'a pas ete posee,
    pas parce que le systeme ne s'est jamais trompe."""
    decisions = [_restitution("corrige") for _ in range(250)]
    corrections = calculer_indicateurs(decisions).corrections
    assert corrections.erreur_fond.valeur == 0.0
    assert corrections.non_declaree.numerateur == corrections.corrigees


def test_la_nature_des_corrections_ne_porte_que_sur_les_restitutions():
    """Un code ADICAP corrige n'a pas de nature au sens clinique. Le melanger
    aux restitutions donnait deux chiffres du meme bloc qui ne decrivaient pas
    la meme population, et le lecteur ne pouvait plus refaire le calcul."""
    decisions = [
        _restitution("corrige", nature="style") for _ in range(10)
    ] + [_code("corrige") for _ in range(10)]
    corrections = calculer_indicateurs(decisions).corrections
    assert corrections.corrigees == 10
    assert corrections.style.denominateur == 10
