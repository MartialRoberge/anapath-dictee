"""Vocabulaire de l'etude : les grilles de decision et le marquage `hative`.

Ces regles sont l'instrument de mesure. Une confusion entre deux grilles
fausserait un taux publie — d'ou ces tests.
"""

from etude.vocabulaire import (
    DECISIONS_COMPLETUDE,
    DECISIONS_RESTITUTION,
    SEUIL_HATIVE_MOTS,
    SEUIL_HATIVE_MS,
    TYPE_CODE,
    TYPE_COMPLETUDE,
    TYPE_RESTITUTION,
    decision_valide,
    est_hative,
)


def test_les_trois_grilles_sont_distinctes():
    """Confondre les grilles fausserait les taux : 'non_dicte' mesure une
    hallucination, 'non_pertinent' mesure un faux positif de completude."""
    assert decision_valide(TYPE_RESTITUTION, "non_dicte")
    assert not decision_valide(TYPE_COMPLETUDE, "non_dicte")
    assert decision_valide(TYPE_COMPLETUDE, "non_pertinent")
    assert not decision_valide(TYPE_RESTITUTION, "non_pertinent")


def test_le_code_autorise_je_ne_sais_pas():
    """Sans cette issue, un praticien qui n'est pas sur valide par defaut et
    l'on mesure de l'acquiescement au lieu de l'exactitude (cahier §3.2)."""
    assert decision_valide(TYPE_CODE, "je_ne_sais_pas")
    assert not decision_valide(TYPE_RESTITUTION, "je_ne_sais_pas")


def test_pertinent_non_retenu_existe_et_n_est_pas_un_rejet():
    """Un praticien qui juge la suggestion pertinente et choisit de ne pas
    l'ecrire valide le systeme : cette valeur ne doit pas etre confondue avec
    'non_pertinent' (cahier §3.3)."""
    assert "pertinent_non_retenu" in DECISIONS_COMPLETUDE
    assert "non_pertinent" in DECISIONS_COMPLETUDE
    assert len(DECISIONS_COMPLETUDE) == 3


def test_decision_inconnue_refusee():
    assert not decision_valide(TYPE_RESTITUTION, "valide")
    assert not decision_valide("type_inexistant", "conforme")


def test_les_quatre_choix_de_restitution():
    assert DECISIONS_RESTITUTION == {
        "conforme", "corrige", "non_dicte", "hors_sujet",
    }


def test_hative_exige_les_deux_conditions():
    """Rapide ET longue. Une decision rapide sur une proposition courte est
    legitime ; c'est la lecture d'un long texte en moins de 1,2 s qui ne l'est pas."""
    assert est_hative(SEUIL_HATIVE_MS - 1, SEUIL_HATIVE_MOTS + 1)
    # rapide mais courte -> legitime
    assert not est_hative(SEUIL_HATIVE_MS - 1, SEUIL_HATIVE_MOTS)
    # longue mais lue -> legitime
    assert not est_hative(SEUIL_HATIVE_MS + 1, SEUIL_HATIVE_MOTS + 1)


def test_hative_tolere_les_valeurs_absentes():
    """Une proposition non encore decidee ne doit pas etre comptee hative."""
    assert not est_hative(None, 30)
    assert not est_hative(500, None)
