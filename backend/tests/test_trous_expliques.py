"""Un trou n'est pas un blanc : c'est une question rattachee a son declencheur.

MARC ne rediger pas a la place du praticien : il structure ce qui a ete dicte et
POINTE ce qui manque. Ce que ces tests tiennent, c'est la qualite du pointage —
un trou doit dire ce qui l'a declenche, pourquoi, et, quand la liste des reponses
est fermee, laquelle choisir.

L'enjeu est la SURINTERPRETATION. Une liste d'options inventee est pire que pas
de liste : on choisit dedans sans la remettre en cause.
"""

from __future__ import annotations

from reports.guardrails import _extract_alertes


def _alerte(**extra: object) -> dict[str, object]:
    base: dict[str, object] = {
        "champ": "grade de dysplasie",
        "description": "Precisez le grade.",
        "section": "conclusion",
    }
    base.update(extra)
    return base


def test_le_declencheur_et_la_raison_arrivent_jusqu_au_modele():
    """Sans eux, le praticien subit la question au lieu de la juger."""
    [alerte] = _extract_alertes(
        {
            "alertes": [
                _alerte(
                    declencheur="adenome tubuleux du colon sigmoide",
                    raison="Un adenome se grade toujours.",
                )
            ]
        }
    )
    assert alerte.declencheur == "adenome tubuleux du colon sigmoide"
    assert alerte.raison == "Un adenome se grade toujours."


def test_une_liste_fermee_devient_un_choix():
    [alerte] = _extract_alertes(
        {"alertes": [_alerte(options=["bas grade", "haut grade"])]}
    )
    assert alerte.options == ["bas grade", "haut grade"]


def test_une_option_unique_n_est_pas_un_choix():
    """Une seule valeur, c'est une reponse pre-remplie deguisee en question —
    exactement ce que le refus d'interpreter existe pour empecher."""
    [alerte] = _extract_alertes({"alertes": [_alerte(options=["haut grade"])]})
    assert alerte.options == []


def test_une_liste_trop_longue_est_rejetee_en_ENTIER_pas_rognee():
    """Une liste tronquee reste une liste : le praticien y choisit sans savoir
    que les valeurs manquantes existaient. Le champ libre est plus honnete."""
    [alerte] = _extract_alertes(
        {"alertes": [_alerte(options=[f"valeur {rang}" for rang in range(12)])]}
    )
    assert alerte.options == []


def test_les_doublons_disparaissent_sans_changer_l_ordre():
    """Deux entrees identiques dans un menu font douter de leur difference."""
    [alerte] = _extract_alertes(
        {"alertes": [_alerte(options=["Saines", "envahies", "saines"])]}
    )
    assert alerte.options == ["Saines", "envahies"]


def test_une_mesure_n_a_pas_d_options():
    """Pour une taille ou un compte, aucune liste ne peut etre fermee. Le
    modele doit laisser vide, et rien ne doit en fabriquer une."""
    [alerte] = _extract_alertes(
        {"alertes": [_alerte(champ="taille de la lesion", options=[])]}
    )
    assert alerte.options == []


def test_un_champ_absent_vaut_None_et_non_chaine_vide():
    """None se lit « le modele n'a rien fourni » et le champ disparait ; une
    chaine vide dessinerait un intitule suivi d'un blanc, qui se lit « il n'y a
    pas de raison »."""
    [alerte] = _extract_alertes({"alertes": [_alerte(declencheur="   ")]})
    assert alerte.declencheur is None
