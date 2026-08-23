"""La courbe d'apprentissage : praticien par praticien, dans l'ordre du temps.

Elle repond a une question precise du protocole : la charge d'edition baisse-t-
elle a mesure qu'un praticien s'habitue ? Si oui, une baisse observee entre le
debut et la fin de l'etude vient de l'accoutumance, pas d'une amelioration de
l'outil — et publier l'un pour l'autre serait une faute.

Deux defauts la rendaient ininterpretable, et ces tests les tiennent fermes.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from routes_etude_admin import MINIMUM_POUR_TERCILES, _apprentissage

DEPART = datetime(2026, 3, 2, 9, 0, tzinfo=UTC)


def _cas(praticien: str, rang: int, edite: int, *, heures: float | None = None):
    """Un dossier reduit a ce dont la courbe a besoin."""
    decalage = rang if heures is None else heures
    return (
        SimpleNamespace(
            cree_a=DEPART + timedelta(hours=decalage),
            caracteres_modifies=edite,
            index_session=rang,
            session_id=f"session-{praticien}",
        ),
        praticien,
    )


def test_la_courbe_ne_melange_plus_les_praticiens():
    """LE DEFAUT QUI ANNULAIT LA MESURE.

    La serie etait concatenee sur tous les praticiens avant d'etre coupee en
    trois. Avec un praticien tres actif et un praticien discret, les trois
    terciles tombaient entierement chez le premier : la courbe publiee etait
    celle d'UNE personne, presentee comme celle de l'etude.

    Ici, l'actif ne bouge pas (300 partout) et le discret s'ameliore beaucoup
    (900 -> 100). Si les praticiens etaient melangees, la courbe serait plate
    ou incoherente ; en les traitant separement, la baisse du second doit se
    voir.
    """
    couples = [_cas("actif", rang, 300) for rang in range(9)]
    couples += [
        _cas("discret", 0, 900, heures=100),
        _cas("discret", 1, 500, heures=101),
        _cas("discret", 2, 100, heures=102),
    ]

    debut, milieu, fin = _apprentissage(couples)[
        "caracteres_modifies_par_tercile"
    ]

    assert debut is not None and fin is not None
    assert debut > fin, (
        "la baisse du praticien discret est noyee par le praticien actif : "
        "la courbe est celle d'une seule personne"
    )
    # Moyenne a poids egal entre les deux : (300 + 900) / 2 puis (300 + 100) / 2.
    assert debut == 600.0
    assert fin == 200.0


def test_l_ordre_est_chronologique_et_non_l_uuid_de_session():
    """L'ordre etait `(session_id, index_session)`, et `session_id` est un UUID
    ALEATOIRE. Une meme personne travaillant sur deux sessions voyait ses cas
    reordonnes au hasard, ce qui suffit a inverser une courbe."""
    couples = [
        (
            SimpleNamespace(
                cree_a=DEPART + timedelta(hours=rang),
                caracteres_modifies=edite,
                index_session=0,  # remis a zero : deuxieme session
                session_id=f"zzz-{9 - rang}",  # ordre inverse de la chronologie
            ),
            "p",
        )
        for rang, edite in enumerate([900, 800, 700, 300, 200, 100])
    ]

    debut, _, fin = _apprentissage(couples)[
        "caracteres_modifies_par_tercile"
    ]
    assert debut is not None and fin is not None
    assert debut > fin, "la courbe est triee sur un identifiant aleatoire"


def test_un_praticien_trop_peu_actif_ne_recoit_pas_de_terciles():
    """On ne coupe pas une serie de deux cas en trois groupes. Le praticien
    reste dans le corpus, mais n'entre pas dans CETTE courbe."""
    couples = [_cas("bref", 0, 500), _cas("bref", 1, 100)]
    resultat = _apprentissage(couples)

    assert resultat["nb_praticiens_retenus"] == 0
    assert resultat["nb_dossiers_retenus"] == 0
    assert resultat["caracteres_modifies_par_tercile"] == [None, None, None], (
        "une moyenne sur zero dossier doit valoir None, jamais zero"
    )
    assert resultat["minimum_par_praticien"] == MINIMUM_POUR_TERCILES


def test_l_effectif_publie_est_celui_des_praticiens():
    """La courbe parle d'accoutumance INDIVIDUELLE : son effectif est un nombre
    de praticiens. N'annoncer que les dossiers laissait croire a une base large
    la ou un seul praticien pouvait tout porter."""
    couples = [_cas("a", r, 200) for r in range(4)]
    couples += [_cas("b", r, 200, heures=50 + r) for r in range(3)]
    couples += [_cas("c", 0, 200, heures=200)]  # trop peu de cas

    resultat = _apprentissage(couples)
    assert resultat["nb_praticiens_retenus"] == 2
    assert resultat["nb_dossiers_retenus"] == 7
