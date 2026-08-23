"""Contrat de la normalisation de texte (source unique tout le backend).

Les caracteres invisibles (insecables, cesure conditionnelle, largeurs nulles)
sont ecrits en \\u volontairement : un editeur ou un outil de copie peut replier
un litteral insecable en espace ordinaire, et le test deviendrait alors vert
sans rien prouver.
"""

from text_utils import strip_accents, normaliser, cle_alphanum

NBSP = "\u00a0"        # espace insecable, semee par Word et le HTML
FINE = "\u202f"        # espace fine insecable, avant ':' en typographie francaise
CESURE = "\u00ad"      # trait d'union conditionnel, invisible
LARGEUR_NULLE = "\u200b"
BOM = "\ufeff"


def test_strip_accents_preserve_la_casse():
    assert strip_accents("Épithélium Malpighien") == "Epithelium Malpighien"


def test_normaliser_minuscule_et_sans_accents():
    assert normaliser("Côlon-Rectum") == "colon-rectum"
    assert normaliser("À PRÉCISER") == "a preciser"


def test_normaliser_ligatures_francaises():
    # Le NFD seul perdrait "oe"/"ae" : on les developpe explicitement.
    assert normaliser("Œsophage") == "oesophage"
    assert normaliser("œsophage") == "oesophage"
    assert normaliser("CŒUR") == "coeur"


def test_cle_alphanum_ignore_ponctuation_et_espaces():
    assert cle_alphanum("pT3, pN1 (8e éd.)") == "pt3pn18eed"
    assert cle_alphanum("Statut  MMR / MSI") == "statutmmrmsi"


def test_idempotence():
    for f in (strip_accents, normaliser, cle_alphanum):
        once = f("Adénocarcinome lépidique")
        assert f(once) == once


# --- Repli de la ponctuation typographique ---------------------------------
#
# Un compte rendu colle depuis Word porte des apostrophes courbes et des
# insecables la ou le clavier tape leurs equivalents ASCII. Sans repli, la
# comparaison de mots-cles echoue SANS erreur et SANS resultat : rien ne
# signale la perte, d'ou ces tests.


def test_apostrophe_courbe_egale_apostrophe_droite():
    assert normaliser("ganglions de l’abdomen") == "ganglions de l'abdomen"
    assert normaliser("‘net’") == "'net'"


def test_guillemets_se_replient_sur_le_guillemet_droit():
    assert normaliser("“net”") == '"net"'
    assert normaliser("«net»") == '"net"'


def test_tirets_typographiques_se_replient_sur_le_trait_d_union():
    assert normaliser("carcinome — infiltrant") == "carcinome - infiltrant"
    assert normaliser("grade 2–3") == "grade 2-3"
    assert normaliser("moins −1") == "moins -1"


def test_points_de_suspension_deviennent_trois_points():
    # Le libelle ADICAP X4M0 ecrit "(PECOME ….)" : sans ce repli il est
    # introuvable pour qui tape trois points.
    assert normaliser("pecome ….") == "pecome ...."


def test_espaces_unicode_deviennent_l_espace_ascii():
    assert normaliser(f"de{NBSP}haut{NBSP}grade") == "de haut grade"
    assert normaliser(f"pT3{FINE}N0") == "pt3 n0"


def test_caracteres_invisibles_sont_effaces():
    # La cesure conditionnelle de Word coupe le mot pour toute comparaison
    # alors qu'elle ne se voit pas a l'ecran.
    assert normaliser(f"adeno{CESURE}carcinome") == "adenocarcinome"
    assert normaliser(f"carcinome{LARGEUR_NULLE}") == "carcinome"
    assert normaliser(f"{BOM}carcinome") == "carcinome"


def test_le_repli_ne_preserve_pas_la_longueur():
    # Contrat explicite : aucun appelant ne doit reporter un offset calcule sur
    # le texte normalise vers le texte d'origine.
    assert len(normaliser("…")) == 3
    assert len(normaliser("œ")) == 2
    assert len(normaliser(CESURE)) == 0


def test_cle_alphanum_ne_voit_pas_le_repli():
    # Aucune ponctuation repliee n'est alphanumerique, donc cette cle rendait
    # deja ces valeurs AVANT le repli. C'est ce qui borne l'effet du changement
    # aux comparaisons de mots-cles : les cles de deduplication ne bougent pas.
    assert cle_alphanum("l’abdomen") == "labdomen"
    assert cle_alphanum("carcinome — infiltrant") == "carcinomeinfiltrant"
    assert cle_alphanum(f"de{NBSP}haut grade") == "dehautgrade"
    assert cle_alphanum("pecome ….") == "pecome"


def test_repli_et_accents_se_composent():
    assert normaliser("L’ÉPITHÉLIUM — « net »…") == "l'epithelium - \" net \"..."


def test_idempotence_apres_repli():
    for f in (strip_accents, normaliser, cle_alphanum):
        once = f(f"L’adéno{CESURE}carcinome — « net »…")
        assert f(once) == once
