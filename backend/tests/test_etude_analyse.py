"""Calcul des indicateurs de l'etude.

Ces tests sont la relecture par les pairs, ecrite d'avance. Chacun defend un
denominateur : c'est la que se joue la difference entre un resultat publiable
et un taux flatteur.
"""

from datetime import UTC, datetime, timedelta

from etude.analyse import (
    DecisionObservee,
    Taux,
    calculer_indicateurs,
    calculer_temps,
    depouiller,
    moyenne,
    terciles,
)
from etude.vocabulaire import TYPE_CODE, TYPE_COMPLETUDE, TYPE_RESTITUTION


def _restitution(decision, hative=False, change=False):
    return DecisionObservee(TYPE_RESTITUTION, decision, hative, None, change)


def _code(decision):
    return DecisionObservee(TYPE_CODE, decision)


def _completude(decision):
    return DecisionObservee(TYPE_COMPLETUDE, decision)


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
