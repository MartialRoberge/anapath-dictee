"""Ne jamais redemander ce que le praticien vient de dire.

CE FICHIER VIENT D'UN CAS REEL, releve par le proprietaire sur une capture.

Sa dictee : « ... TTF1+, PD-L1, 5%, analyse difficile, ALK negatif. »
Ce que MARC a produit : « PD-L1 : [A COMPLETER: pourcentage de cellules
tumorales positives] ».

Il a dit 5 %. On le lui redemande. Il a parle pour ne pas avoir a taper, et on
lui rend un formulaire — c'est la pire chose que l'outil puisse faire.

La regle existait deja dans le prompt de redaction, en toutes lettres et avec
son exemple. Elle n'a pas suffi : sur une dictee telegraphique, le modele ne
rattache pas la valeur a son etiquette. Une regle qui echoue sur le cas normal
n'est pas une regle. Ces tests tiennent la version deterministe.
"""

from __future__ import annotations

from reports.comblement import combler_depuis_la_dictee

DICTEE = (
    "Biopsie d'une lesion pulmonaire du lobe inferieur droit, une carotte, "
    "5 mm, deux plans de coupe. Proliferation tumorale, cellules fortement "
    "atypiques. TTF1+, PD-L1, 5%, analyse difficile, ALK negatif."
)


def test_le_pourcentage_dicte_comble_le_trou():
    """LE CAS RELEVE. Et l'unite compte : « 5 » au lieu de « 5% » serait une
    erreur clinique, pas une coquette."""
    cr = "- PD-L1 : [A COMPLETER: pourcentage de cellules tumorales positives]"
    sortie, combles = combler_depuis_la_dictee(cr, DICTEE)
    assert sortie == "- PD-L1 : 5%"
    assert len(combles) == 1
    assert combles[0].valeur == "5%"


def test_le_comblement_porte_sa_source():
    """Un comblement qu'on ne peut pas justifier serait indistinguable d'une
    invention. Le passage de la dictee est recopie, jamais reformule."""
    cr = "- ALK : [A COMPLETER: resultat]"
    _, combles = combler_depuis_la_dictee(cr, DICTEE)
    assert "ALK" in combles[0].source
    assert "negatif" in combles[0].source


def test_un_champ_absent_de_la_dictee_reste_un_trou():
    """Sinon on aurait remplace la machine a redemander par une machine a
    inventer, ce qui est pire."""
    cr = "- Ki67 : [A COMPLETER: pourcentage]"
    sortie, combles = combler_depuis_la_dictee(cr, DICTEE)
    assert sortie == cr
    assert combles == []


def test_une_etiquette_ambigue_reste_un_trou():
    """Deux valeurs pour une meme etiquette : on ne peut pas choisir, et
    choisir au hasard ecrirait un chiffre faux dans un compte rendu signe."""
    dictee = "Premier prelevement, taille 12 mm. Second prelevement, taille 30 mm."
    cr = "- taille : [A COMPLETER: taille de la lesion]"
    sortie, combles = combler_depuis_la_dictee(cr, dictee)
    assert sortie == cr
    assert combles == []


def test_une_valeur_trop_loin_de_son_etiquette_ne_compte_pas():
    """C'est le faux ancrage qu'on a deja paye une fois : un « 5 % » trente
    mots apres « PD-L1 » ne se rattache pas a lui."""
    dictee = (
        "PD-L1 sur la lame du bas, analyse difficile, il faudra recouper le "
        "bloc et revoir la coloration avant de conclure quoi que ce soit, 5%."
    )
    cr = "- PD-L1 : [A COMPLETER: pourcentage]"
    sortie, _ = combler_depuis_la_dictee(cr, dictee)
    assert sortie == cr


def test_une_phrase_n_est_jamais_une_valeur():
    """Inserer une phrase entiere a la place d'un champ serait du remplissage,
    pas de la restitution."""
    dictee = "Grade : la lesion parait tout a fait banale a l'examen."
    cr = "- Grade : [A COMPLETER: grade histopronostique]"
    sortie, _ = combler_depuis_la_dictee(cr, dictee)
    assert sortie == cr


def test_plusieurs_trous_sont_combles_chacun_avec_sa_valeur():
    cr = (
        "**Immunohistochimie :**\n"
        "- TTF1 : [A COMPLETER: resultat]\n"
        "- PD-L1 : [A COMPLETER: pourcentage]\n"
        "- ALK : [A COMPLETER: resultat]\n"
    )
    sortie, combles = combler_depuis_la_dictee(cr, DICTEE)
    assert "PD-L1 : 5%" in sortie
    assert "ALK : negatif" in sortie
    assert len(combles) >= 2
    assert "[A COMPLETER" not in sortie.split("ALK")[1]
