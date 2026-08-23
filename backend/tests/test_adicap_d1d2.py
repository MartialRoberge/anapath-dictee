"""Contrat du codeur D1/D2 (``adicap_d1d2``), pose sur la table de decision.

Chaque test nomme la regle du JSON qu'il protege. Une partie d'entre eux fige
des cas que le codeur historique traite FAUX : mucosectomie avale par -ectomie,
biopsie guidee codee B, LBA absorbe par L, congelation codee E, et surtout un
defaut B pose la ou la table exige une abstention.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from adicap_d1d2 import (
    _CAS_PARTICULIERS,
    _TABLE_PATH,
    CODES_RARES,
    D1_CYTOLOGIQUES,
    coder_d1,
    coder_d2,
    composer_codes,
    d7_autorise,
    libelle_d1,
    libelle_d2,
)

TABLE: dict[str, object] = json.loads(Path(_TABLE_PATH).read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# Ordre d'evaluation : K avant toute morphologie en -ectomie
# ---------------------------------------------------------------------------


def test_mucosectomie_donne_k_et_non_une_exerese():
    resultat = coder_d1("mucosectomie oesophagienne")
    assert resultat.code == "K"
    # L'origine prouve que K a bien ete atteint par l'acte simple (etape 3) et
    # non par la famille exerese (etape 5), qui l'aurait pris pour un -ectomie.
    assert resultat.origine == "acte_simple"


def test_polypectomie_endoscopique_donne_k():
    resultat = coder_d1("polypectomie endoscopique du sigmoide")
    assert resultat.code == "K"
    assert resultat.origine == "acte_simple"


def test_curetage_donne_k():
    assert coder_d1("produit de curetage uterin").code == "K"


def test_resection_transuretrale_donne_k():
    assert coder_d1("resection transuretrale de vessie").code == "K"


# ---------------------------------------------------------------------------
# Famille biopsie : elle existe, et elle a des modificateurs
# ---------------------------------------------------------------------------


def test_biopsie_sous_scanner_donne_h():
    resultat = coder_d1("biopsie hepatique sous scanner")
    assert resultat.code == "H"
    assert resultat.origine == "famille_biopsie"


def test_biopsie_cutanee_par_punch_donne_p():
    resultat = coder_d1("biopsie cutanee par punch")
    assert resultat.code == "P"
    assert resultat.origine == "famille_biopsie"


def test_biopsie_chirurgicale_donne_b():
    assert coder_d1("biopsie chirurgicale ganglionnaire").code == "B"


def test_biopsie_endomyocardique_donne_t():
    assert coder_d1("biopsie endomyocardique").code == "T"


def test_pluriel_simple_tolere_sur_la_base():
    # La dictee dit "deux biopsies bronchiques" : le 's' final ne doit pas faire
    # manquer la base.
    assert coder_d1("deux biopsies bronchiques").code == "P"


def test_biopsie_sans_modificateur_propose_la_question_de_guidage():
    resultat = coder_d1("biopsie hepatique")
    assert resultat.candidats == ("H", "P")
    assert resultat.question_id == "d1_guidage_biopsie"


# ---------------------------------------------------------------------------
# Famille cytoponction
# ---------------------------------------------------------------------------


def test_cytoponction_echoguidee_donne_g_avec_les_propositions():
    # 'echoguidee' est marque a_valider pour la cytoponction dans le JSON : le
    # code G n'est atteignable qu'en activant les propositions.
    resultat = coder_d1("cytoponction thyroidienne echoguidee", inclure_propositions=True)
    assert resultat.code == "G"
    assert resultat.origine == "famille_cytoponction"


def test_cytoponction_echoguidee_reste_au_defaut_c_sans_les_propositions():
    resultat = coder_d1("cytoponction thyroidienne echoguidee")
    assert resultat.code == "C"
    assert resultat.question_id == "d1_guidage_cytoponction"


def test_cytoponction_guidee_par_imagerie_donne_g_sans_proposition():
    # 'guidee par imagerie' est valide, lui : il doit sortir G par defaut.
    assert coder_d1("cytoponction guidee par imagerie").code == "G"


# ---------------------------------------------------------------------------
# Famille exerese : le discriminant I / O, et l'abstention quand il manque
# ---------------------------------------------------------------------------


def test_appendicectomie_donne_o():
    resultat = coder_d1("appendicectomie")
    assert resultat.code == "O"
    assert resultat.origine == "famille_exerese"


def test_lobectomie_donne_i():
    resultat = coder_d1("lobectomie superieure droite")
    assert resultat.code == "I"
    assert resultat.origine == "famille_exerese"


def test_conisation_donne_i_sans_base_ni_suffixe():
    # 'conisation' n'a ni base 'piece'/'exerese' ni suffixe -ectomie : la table
    # geste x organe doit quand meme la reconnaitre.
    assert coder_d1("conisation du col uterin").code == "I"


def test_geste_exerese_absent_des_deux_listes_donne_une_abstention():
    resultat = coder_d1("thyroidectomie")
    assert resultat.abstention
    assert resultat.code is None
    assert set(resultat.candidats) == {"I", "O"}
    assert resultat.question_id == "d1_exerese_i_o"


def test_piece_operatoire_sans_geste_nomme_sabstient():
    resultat = coder_d1("piece operatoire adressee a l'etat frais")
    assert resultat.abstention
    assert set(resultat.candidats) == {"I", "O"}


def test_le_geste_precis_lemporte_sur_le_geste_partiel_homonyme():
    assert coder_d1("thyroidectomie totale").code == "O"
    assert coder_d1("hemithyroidectomie gauche").code == "I"


def test_sortie_de_la_table_exerese_est_marquee_a_valider():
    # La table geste x organe porte le statut "PROPOSITION DE DEPART" : elle est
    # active, mais chaque sortie doit rester signalee a la revue.
    assert coder_d1("appendicectomie").a_valider is True


# ---------------------------------------------------------------------------
# Pas de correspondance en sous-chaine
# ---------------------------------------------------------------------------


def test_cytoponction_pleurale_nest_pas_une_ponction_pleurale():
    # En sous-chaine, 'ponction pleurale' se trouve au milieu de
    # 'cytoponction pleurale' et sortirait L. A limites de mot, c'est la famille
    # cytoponction qui repond.
    resultat = coder_d1("cytoponction pleurale", inclure_propositions=True)
    assert resultat.code == "C"
    assert resultat.origine == "famille_cytoponction"


def test_hemicolectomie_nest_pas_une_colectomie_totale():
    # En sous-chaine, 'colectomie' se trouve dans 'hemicolectomie' et sortirait O.
    assert coder_d1("hemicolectomie droite").code == "I"


def test_lavage_nest_pas_absorbe_par_liquide():
    assert coder_d1("lavage broncho-alveolaire").code == "R"
    assert coder_d1("LBA du lobe superieur droit").code == "R"
    assert coder_d1("lavage peritoneal").code == "R"


def test_liquide_demis_reste_en_l():
    assert coder_d1("liquide pleural").code == "L"
    assert coder_d1("liquide cephalo-rachidien").code == "L"


def test_aspiration_a_laiguille_ne_declenche_pas_lacte_simple_a():
    # Garde explicite du JSON : l'aspiration a l'aiguille releve de la
    # cytoponction, jamais de l'aspiration bronchique.
    assert coder_d1("aspiration a l'aiguille fine", inclure_propositions=True).code == "C"
    assert coder_d1("aspiration bronchique").code == "A"


# ---------------------------------------------------------------------------
# Abstention : jamais de defaut fabrique
# ---------------------------------------------------------------------------


def test_aucun_geste_dicte_donne_une_abstention_et_non_un_defaut_b():
    resultat = coder_d1("Adenocarcinome peu differencie.")
    assert resultat.abstention
    assert resultat.candidats == ()
    assert resultat.question_id == ""


def test_texte_vide_sabstient():
    assert coder_d1("").abstention


# ---------------------------------------------------------------------------
# Codes rares N, V, X : syntagme complet exact et rien d'autre
# ---------------------------------------------------------------------------


def test_necropsie_donne_n():
    resultat = coder_d1("necropsie")
    assert resultat.code == "N"
    assert resultat.origine == "code_rare"


def test_prelevement_veterinaire_donne_v_mais_veterinaire_seul_sabstient():
    assert coder_d1("prelevement veterinaire").code == "V"
    assert coder_d1("adresse par le cabinet veterinaire").abstention


def test_experimentation_donne_x():
    assert coder_d1("protocole d'experimentation").code == "X"


def test_autopsie_est_une_proposition_donc_inerte_par_defaut():
    assert coder_d1("autopsie medico-legale").abstention
    assert coder_d1("autopsie medico-legale", inclure_propositions=True).code == "N"


def test_codes_rares_ne_tolerent_pas_le_pluriel():
    # La regle interdit d'atteindre N, V, X par morphologie : le 's' en est une.
    assert coder_d1("necropsies").abstention


# ---------------------------------------------------------------------------
# Entrees a_valider : inertes par defaut, documentees
# ---------------------------------------------------------------------------


def test_liste_s_entierement_a_valider_reste_inerte_par_defaut():
    # Le JSON marque TOUTE la liste S comme a valider (les en-tetes R et S
    # avaient fusionne dans le document source).
    assert coder_d1("crachat matinal").abstention
    assert coder_d1("crachat matinal", inclure_propositions=True).code == "S"


def test_frottis_cervico_uterin_est_une_proposition_mais_frottis_reste_valide():
    assert coder_d1("frottis cervico-uterin").code == "F"
    assert coder_d1("brossage bronchique").code == "F"


def test_cas_particuliers_de_la_biopsie_sont_des_propositions():
    assert coder_d1("macrobiopsie mammaire").abstention
    assert coder_d1("macrobiopsie mammaire", inclure_propositions=True).code == "H"
    # tru-cut n'impose aucun code : il se comporte comme une base nue.
    assert coder_d1("tru-cut hepatique", inclure_propositions=True).code == "P"


def test_cas_particuliers_du_module_couvrent_exactement_ceux_du_json():
    # Garde anti-derive : si le referentiel ajoute un cas particulier, le module
    # doit dire quoi en faire au lieu d'echouer silencieusement.
    familles = TABLE["familles"]
    attendus = set(familles["biopsie"]["cas_particuliers_a_valider"])
    assert set(_CAS_PARTICULIERS) == attendus


# ---------------------------------------------------------------------------
# Position 2 : primaire H / C
# ---------------------------------------------------------------------------


def test_d2_defaut_est_h():
    resultat = coder_d2("biopsie bronchique")
    assert resultat.primaire == "H"
    assert resultat.motif == "defaut"


def test_d2_declencheur_cytologique_donne_c():
    assert coder_d2("etalement cytologique").primaire == "C"
    assert coder_d2("cytocentrifugation du liquide").primaire == "C"


def test_cytobloc_apres_cytoponction_pleurale_donne_d2_h():
    d1 = coder_d1("cytobloc apres cytoponction pleurale")
    resultat = coder_d2("cytobloc apres cytoponction pleurale", d1.code)
    # Un cytobloc est une inclusion : H, malgre le declencheur 'cytoponction'
    # et malgre K1 qui reclamerait C pour un D1 cytologique.
    assert d1.code == "C"
    assert resultat.primaire == "H"
    assert "cytobloc" in resultat.motif


def test_inclusion_en_paraffine_annule_le_declencheur_cytologique():
    assert coder_d2("frottis puis inclusion en paraffine").primaire == "H"
    assert coder_d2("cell-block realise apres cytoponction").primaire == "H"


# ---------------------------------------------------------------------------
# Position 2 : les sept codes secondaires
# ---------------------------------------------------------------------------


def test_congelation_donne_le_secondaire_k_et_jamais_e():
    resultat = coder_d2("prelevement place en congelation")
    assert "K" in resultat.secondaires
    assert "E" not in resultat.secondaires


def test_extemporane_donne_le_secondaire_e():
    assert coder_d2("examen extemporane per-operatoire").secondaires == ("E",)


def test_secondaires_multiples_dans_lordre_de_la_table():
    resultat = coder_d2(
        "Extemporane, congelation en tumorotheque, recherche de mutation EGFR."
    )
    assert resultat.secondaires == ("E", "K", "Y")


def test_secondaires_ne_remplacent_jamais_le_primaire():
    resultat = coder_d2("relecture de lames, microscopie electronique")
    assert resultat.primaire == "H"
    assert set(resultat.secondaires) == {"L", "U"}


def test_aucun_code_inactif_nest_jamais_predit():
    inactifs = set(TABLE["D2"]["codes_inactifs"]["codes"])
    textes = (
        "immunohistochimie realisee sur la biopsie",
        "macroscopie : piece de 4 cm",
        "coloration speciale au PAS",
        "biopsie prostatique",
    )
    for texte in textes:
        resultat = coder_d2(texte)
        assert resultat.primaire not in inactifs
        assert not set(resultat.secondaires) & inactifs


def test_immunohistochimie_ne_produit_aucun_code_d2():
    # L'IHC releve de la cotation, pas de la codification : elle ne doit rien
    # declencher, ni en primaire ni en secondaire.
    resultat = coder_d2("etude immunohistochimique complementaire")
    assert resultat.primaire == "H"
    assert resultat.secondaires == ()


# ---------------------------------------------------------------------------
# Regles de coherence K1 a K5
# ---------------------------------------------------------------------------


def test_k1_un_d1_cytologique_impose_c():
    for d1 in sorted(D1_CYTOLOGIQUES):
        assert coder_d2("compte rendu sans mention de technique", d1).primaire == "C"


def test_k1_exception_inclusion():
    assert coder_d2("cytobloc realise", "L").primaire == "H"


def test_k1_un_d1_non_cytologique_reste_en_h():
    for d1 in ("B", "O", "I", "K", "P", "H", "T"):
        assert coder_d2("compte rendu sans mention de technique", d1).primaire == "H"


def test_k1_liste_cytologique_conforme_au_json():
    # Garde anti-derive : la liste est ecrite en prose dans la regle K1.
    regles = TABLE["coherence_inter_positions"]
    k1 = next(r["regle"] for r in regles if r["id"] == "K1")
    lettres = re.search(r"\(([A-Z,]+)\)", k1).group(1).split(",")
    assert D1_CYTOLOGIQUES == frozenset(lettres)


def test_k2_et_k3_gouvernent_lacces_a_d7():
    assert d7_autorise("C") is True
    assert d7_autorise("H") is False


def test_k4_un_secondaire_ne_change_que_la_position_2():
    d2 = coder_d2("Extemporane. Recherche de mutation EGFR.")
    codes = composer_codes("P", d2, "RB....")
    primaire = codes[0].code
    for code in codes[1:]:
        assert code.code[0] == primaire[0]
        assert code.code[2:] == primaire[2:]
        assert code.code[1] != primaire[1]


def test_k5_aucun_secondaire_sans_primaire():
    d2 = coder_d2("Extemporane. Recherche de mutation EGFR.")
    codes = composer_codes("P", d2, "RB....")
    assert codes[0].role == "primaire"
    assert [c.role for c in codes[1:]] == ["secondaire"] * (len(codes) - 1)


def test_composer_refuse_un_code_de_longueur_invalide():
    d2 = coder_d2("biopsie")
    with pytest.raises(ValueError):
        composer_codes("P", d2, "RB")
    with pytest.raises(ValueError):
        composer_codes("PP", d2, "RB....")


# ---------------------------------------------------------------------------
# Cardinalite : un primaire, n secondaires
# ---------------------------------------------------------------------------


def test_cardinalite_un_primaire_plus_un_code_par_technique():
    d2 = coder_d2("Extemporane, congelation, recherche de fusion.")
    codes = composer_codes("P", d2, "RB....")
    assert len(codes) == 1 + len(d2.secondaires)
    assert len(codes) == 4


def test_sans_technique_un_seul_code():
    d2 = coder_d2("biopsie bronchique")
    assert composer_codes("P", d2, "RB....") == composer_codes("P", d2, "RB....")
    assert len(composer_codes("P", d2, "RB....")) == 1


def test_exemple_de_cardinalite_du_json():
    # Prelevement 1 de l'exemple : biopsie bronchique, extemporane, EGFR.
    d1 = coder_d1("deux biopsies bronchiques")
    d2 = coder_d2("Extemporane sur la premiere. Recherche de mutation EGFR.")
    codes = [c.code for c in composer_codes(d1.code, d2, "RB....")]
    assert codes == ["PHRB....", "PERB....", "PYRB...."]


def test_exemple_de_cardinalite_du_json_prelevement_lba():
    # Prelevement 3 de l'exemple : le LBA sort en R, et K1 le rend cytologique.
    d1 = coder_d1("lavage broncho-alveolaire")
    d2 = coder_d2("lavage broncho-alveolaire", d1.code)
    codes = [c.code for c in composer_codes(d1.code, d2, "RP....")]
    assert codes == ["RCRP...."]


# ---------------------------------------------------------------------------
# Libelles
# ---------------------------------------------------------------------------


def test_chaque_code_emis_porte_un_libelle():
    for texte in ("appendicectomie", "biopsie hepatique", "necropsie", "lavage gastrique"):
        resultat = coder_d1(texte)
        assert resultat.libelle
        assert libelle_d1(resultat.code) == resultat.libelle


def test_libelles_d2_couvrent_primaires_et_secondaires():
    assert libelle_d2("H")
    assert libelle_d2("C")
    for secondaire in ("E", "F", "G", "K", "L", "U", "Y"):
        assert libelle_d2(secondaire)
    assert libelle_d2("I") == ""


def test_codes_rares_declares_conformes_au_json():
    assert CODES_RARES == frozenset(TABLE["codes_rares"]["codes"])
