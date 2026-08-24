"""Le chiffre invente dans une phrase dont tous les mots sont dictes.

CE TEST VIENT D'UN CAS REEL, pas d'une hypothese. Sur un des cinq audios de
pathologistes du corpus, MARC a produit :

    « L'etude histologique des ganglions ne montre pas de metastase
      ganglionnaire (0/22 ganglions examines). »

La dictee enumere cinq ganglions peribronchiques, deux intraparenchymateux et
trois sous-carinaires. Elle ne dit jamais 22, ni en chiffres ni en lettres.
Chaque MOT de la phrase, lui, est dans la dictee — si bien que l'ancrage la
declarait soutenue, le college l'a affirmee a l'unanimite, et elle ne serait
jamais remontee au praticien.

Le denominateur ganglionnaire n'est pas un detail : il dit si le curage est
adequat, donc si le pN0 est fiable. C'est exactement le type d'erreur que
l'etude existe pour attraper.
"""

from __future__ import annotations

from etude.extraction import extraire_restitutions, extraire_restitutions_arbitrees
from reports.numbers import chiffres_non_dictes

DICTEE = (
    "Lobectomie inferieure droite. Lesion blanchatre mal limitee, heterogene, "
    "18, 17, 14 mm. Cinq ganglions peribronchiques. Deux ganglions "
    "intraparenchymateux. Trois sous-carinaires. Pas de metastase."
)
PHRASE_FAUTIVE = (
    "L'etude histologique des ganglions ne montre pas de metastase "
    "ganglionnaire (0/22 ganglions examines)."
)


def test_le_chiffre_invente_est_detecte_alors_que_les_mots_sont_dictes():
    """Le coeur du defaut : mot et chiffre sont deux preuves distinctes."""
    assert chiffres_non_dictes(PHRASE_FAUTIVE, DICTEE) == ("22 ganglion",)


def test_une_mesure_reellement_dictee_ne_declenche_rien():
    """Sinon le signal serait du bruit, et le praticien cesserait de le lire."""
    assert chiffres_non_dictes("La lesion mesure 18 mm.", DICTEE) == ()
    assert chiffres_non_dictes("Elle mesure 17 mm sur 14 mm.", DICTEE) == ()


def test_un_nombre_dicte_en_toutes_lettres_soutient_sa_forme_chiffree():
    """« cinq ganglions » dicte doit soutenir « 5 ganglions » ecrit."""
    assert chiffres_non_dictes("Cinq ganglions preleves : 5 ganglions.", DICTEE) == ()


def test_une_numerotation_de_bloc_n_est_pas_une_donnee_clinique():
    """Le pathologiste dicte rarement chaque numero de bloc. Les signaler
    ferait du bruit sur ce qui n'est qu'un rangement."""
    assert chiffres_non_dictes("Inclusion en totalite (bloc 42).", DICTEE) == ()


def test_une_annee_n_est_pas_une_mesure():
    assert chiffres_non_dictes("Anteriorite de 2019, 12 mm.", DICTEE + " douze") == ()


def test_l_assertion_fautive_remonte_avec_son_chiffre_signale():
    """Bout en bout : elle est extraite, elle est ancree par ses mots, et elle
    porte quand meme le signal qui la rend suspecte."""
    cr = f"**Microscopie :**\n{PHRASE_FAUTIVE}"
    propositions = extraire_restitutions(cr, DICTEE)
    visee = [p for p in propositions if "22" in p.valeur_proposee]
    assert visee, "l'assertion n'est meme pas extraite"
    assert visee[0].ancree is True, (
        "elle EST ancree par ses mots : c'est tout le probleme, et le signal "
        "des chiffres doit etre independant de l'ancrage"
    )
    assert visee[0].chiffres_non_dictes == ("22 ganglion",)


def test_le_college_ne_peut_pas_faire_taire_un_chiffre_invente():
    """LE VERROU. Le college avait affirme cette phrase a l'unanimite : son
    sens est intact et ses mots sont dictes. Sans exception explicite, elle ne
    serait jamais parvenue au praticien.

    La verification des chiffres est deterministe et ne depend d'aucun modele.
    C'est precisement pour cela qu'on ne la delegue pas au college.
    """
    soumissions = [
        {
            "assertion": PHRASE_FAUTIVE,
            "section": "microscopie",
            "comportement": "AFFIRMER",  # le college est unanime et rassurant
        },
        {
            "assertion": "La lesion mesure 18 mm.",
            "section": "macroscopie",
            "comportement": "AFFIRMER",
        },
    ]
    retenues = extraire_restitutions_arbitrees(soumissions, DICTEE)
    valeurs = [p.valeur_proposee for p in retenues]

    assert PHRASE_FAUTIVE in valeurs, (
        "le college a fait taire un chiffre invente : l'erreur atteint le "
        "compte rendu final sans que le praticien l'ait jamais vue"
    )
    assert "La lesion mesure 18 mm." not in valeurs, (
        "une assertion saine affirmee par le college ne doit PAS etre soumise : "
        "faire reconfirmer ce qui est verifie dilue l'attention"
    )
