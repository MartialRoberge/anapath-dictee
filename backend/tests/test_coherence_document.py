"""Couche 2 — coherence documentaire deterministe (C1 a C17).

Deux exigences opposees, testees separement :

* un CR bien forme ne declenche AUCUNE alerte (batterie ``CR_CONFORMES``, qui
  couvre les pieges connus : CR bilateral, multi-organes, enumeration partielle
  de stations, negation correcte, blocs complementaires) ;
* chaque regle se declenche sur son cas fautif, avec le bon identifiant.
"""

import pytest

from reports.coherence_document import (
    REGLES_NON_EVALUABLES,
    AlerteDocument,
    decouper_sections,
    regle_c1_blocs_continus,
    regle_c1_blocs_uniques,
    regle_c2_nombre_de_prelevements,
    regle_c3_somme_des_ganglions,
    regle_c4_envahis_inferieur_examines,
    regle_c5_fragments,
    regle_c6_taille_conclusion,
    regle_c7_unites_homogenes,
    regle_c8_trois_axes,
    regle_c9_marges_presentes,
    regle_c10_lesion_conclue_decrite,
    regle_c11_marqueur_conclu_documente,
    regle_c12_negation_contredite,
    regle_c12_negation_de_normalite,
    regle_c13_lateralite,
    regle_c14_organe,
    regle_c15_marges_mesurees,
    regle_c16_ganglions_envahis,
    regle_c16_ganglions_examines,
    verifier_coherence_document,
)

# ---------------------------------------------------------------------------
# Comptes rendus bien formes : aucune alerte attendue
# ---------------------------------------------------------------------------

CR_SEIN = """**__PIECE DE TUMORECTOMIE DU SEIN DROIT__**

**Macroscopie :**
Pièce de tumorectomie orientée, pesant 42 g, mesurant 55 x 40 x 30 mm.
À la coupe, lésion tumorale ferme, blanchâtre, de 18 mm de grand axe,
située à 6 mm de la limite la plus proche. Inclusion en 6 blocs (blocs 1 à 6).
Curage axillaire : 12 ganglions isolés.

**Microscopie :**
Carcinome infiltrant de type non spécifique, grade SBR 2.
Absence d'emboles vasculaires. Les limites d'exérèse sont saines,
la plus proche à 6 mm. 12 ganglions examinés dont 2 métastatiques.
RE positifs, RP positifs, HER2 score 1+, Ki67 15%.

**__CONCLUSION :__**
**Carcinome infiltrant de type non spécifique du sein droit, 18 mm, grade SBR 2.
Limites d'exérèse saines (6 mm). 2 ganglions métastatiques sur 12 examinés.
HER2 négatif, Ki67 15%.**
"""

CR_POUMON = """**__LOBECTOMIE SUPERIEURE DROITE ET CURAGE MEDIASTINAL__**

**Macroscopie :**
1) Pièce de lobectomie supérieure droite mesurant 140 x 95 x 45 mm.
Lésion tumorale de 32 mm de grand axe, à 15 mm de la tranche de section bronchique.
Inclusion en 8 blocs (blocs 1 à 8).
2) Curage médiastinal : station 4R : 5 ganglions ; station 7 : 6 ganglions ;
station 10 : 3 ganglions. Au total 14 ganglions.

**Microscopie :**
1) Adénocarcinome pulmonaire peu différencié. Tranche de section bronchique saine, à 15 mm.
TTF1 positif, p40 négatif.
2) 14 ganglions examinés dont 3 métastatiques.

**__CONCLUSION :__**
**1) Adénocarcinome pulmonaire du lobe supérieur droit, 32 mm, TTF1 positif.
2) 3 ganglions métastatiques sur 14 examinés.**
"""

CR_COLON = """**__COLECTOMIE DROITE__**

**Macroscopie :**
Pièce de colectomie droite mesurant 25 x 6 x 4 cm.
Lésion ulcéro-bourgeonnante de 45 mm de grand axe, à 60 mm de la limite d'exérèse
distale. Inclusion en 12 blocs (blocs 1 à 12). Curage : 22 ganglions isolés.

**Microscopie :**
Adénocarcinome lieberkühnien moyennement différencié infiltrant la sous-séreuse.
Limites d'exérèse saines, la plus proche à 60 mm.
22 ganglions examinés dont 0 métastatique. MLH1, MSH2, MSH6 et PMS2 conservés.

**__CONCLUSION :__**
**Adénocarcinome colique moyennement différencié, 45 mm.
Limites d'exérèse saines. 0 ganglion métastatique sur 22 examinés.
Protéines MLH1, MSH2, MSH6 et PMS2 conservées.**
"""

CR_BIOPSIES_BILATERALES = """**__BIOPSIES MAMMAIRES BILATERALES__**

**Macroscopie :**
1) Sein droit : deux carottes de 12 mm.
2) Sein gauche : deux carottes de 14 mm.

**Microscopie :**
1) Carcinome infiltrant de type non spécifique, grade SBR 2.
2) Adénose sclérosante, sans atypie.

**__CONCLUSION :__**
**1) Sein droit : carcinome infiltrant de type non spécifique, grade SBR 2.
2) Sein gauche : lésion bénigne, adénose sclérosante.**
"""

CR_MULTI_ORGANE = """**__BIOPSIES ETAGEES OESOPHAGE, ESTOMAC ET DUODENUM__**

**Macroscopie :**
Trois prélèvements.
1) Œsophage : deux fragments de 3 mm.
2) Estomac : trois fragments de 4 mm.
3) Duodénum : deux fragments de 3 mm.

**Microscopie :**
1) Muqueuse malpighienne œsophagienne sans particularité.
2) Gastrite chronique atrophique, Helicobacter pylori non retrouvé.
3) Muqueuse duodénale normale, sans atrophie villositaire.

**__CONCLUSION :__**
**1) Œsophage : muqueuse sans particularité.
2) Estomac : gastrite chronique atrophique.
3) Duodénum : muqueuse sans anomalie.**
"""

CR_CYTOLOGIE = """**__CYTOPONCTION THYROIDIENNE DROITE__**

**Macroscopie :**
Deux lames et un culot cellulaire.

**Etude cytologique :**
Frottis de richesse satisfaisante. Absence de cellule anormale.
Colloïde abondante, cellules vésiculaires régulières.

**__CONCLUSION :__**
**Cytoponction thyroïdienne droite : lésion bénigne, catégorie II de Bethesda.**
"""

CR_PEAU = """**__EXERESE CUTANEE DU DOS__**

**Macroscopie :**
Fuseau cutané de 30 x 12 mm, épaisseur 8 mm.
Lésion pigmentée de 9 mm de grand axe, à 6 mm de la recoupe latérale la plus proche.

**Microscopie :**
Mélanome à extension superficielle, indice de Breslow 1,2 mm, sans ulcération.
Recoupes latérales et profonde saines, la plus proche à 6 mm.

**__CONCLUSION :__**
**Mélanome à extension superficielle, Breslow 1,2 mm, recoupes saines (6 mm).**
"""

CR_LYMPHOME = """**__BIOPSIE GANGLIONNAIRE CERVICALE GAUCHE__**

**Macroscopie :**
Ganglion mesurant 25 x 18 x 12 mm.

**Microscopie :**
Prolifération lymphomateuse diffuse à grandes cellules B.
CD20 positif, CD3 négatif, BCL2 positif, Ki67 80%.

**__CONCLUSION :__**
**Lymphome B diffus à grandes cellules, CD20 positif, Ki67 80%.**
"""

CR_BLOCS_COMPLEMENTAIRES = """**__COMPLEMENT D'ETUDE — BIOPSIE HEPATIQUE__**

**Microscopie :**
Recoupes profondes réalisées sur les blocs 4 et 5.
Stéatose macrovésiculaire, fibrose portale.

**__CONCLUSION :__**
**Stéatose macrovésiculaire avec fibrose portale.**
"""

CR_CONFORMES: dict[str, str] = {
    "sein": CR_SEIN,
    "poumon": CR_POUMON,
    "colon": CR_COLON,
    "bilateral": CR_BIOPSIES_BILATERALES,
    "multi_organe": CR_MULTI_ORGANE,
    "cytologie": CR_CYTOLOGIE,
    "peau": CR_PEAU,
    "lymphome": CR_LYMPHOME,
    "blocs_complementaires": CR_BLOCS_COMPLEMENTAIRES,
}


@pytest.mark.parametrize("nom", sorted(CR_CONFORMES))
def test_aucun_faux_positif_sur_cr_bien_forme(nom):
    alertes = verifier_coherence_document(CR_CONFORMES[nom])
    assert alertes == [], (
        f"CR '{nom}' bien forme mais signale : "
        + " | ".join(f"{a.regle}: {a.message}" for a in alertes)
    )


# ---------------------------------------------------------------------------
# Une alerte par regle : cas fautif
# ---------------------------------------------------------------------------

CAS_FAUTIFS: list[tuple[str, object, str]] = [
    (
        "C1",
        regle_c1_blocs_continus,
        "Inclusion en blocs 1, 2, 3 et 5.",
    ),
    (
        "C1",
        regle_c1_blocs_uniques,
        "1) Tumeur du lobe supérieur, blocs 1 à 8.\n2) Curage, bloc 8.\n",
    ),
    (
        "C2",
        regle_c2_nombre_de_prelevements,
        "Deux prélèvements adressés.\n1) Estomac.\n2) Duodénum.\n3) Côlon.\n",
    ),
    (
        "C3",
        regle_c3_somme_des_ganglions,
        "Station 4R : 5 ganglions ; station 7 : 2 ganglions ; station 10 : 3 "
        "ganglions ; station 11 : 1 ganglion ; station 12 : 2 ganglions. "
        "Au total 14 ganglions.",
    ),
    (
        "C4",
        regle_c4_envahis_inferieur_examines,
        "3 ganglions métastatiques sur 2 examinés.",
    ),
    (
        "C5",
        regle_c5_fragments,
        "**Macroscopie :**\nTrois fragments.\n"
        "**Microscopie :**\nLes 2 fragments sont sains.\n",
    ),
    (
        "C6",
        regle_c6_taille_conclusion,
        "**Macroscopie :**\nLésion de 18 mm de grand axe.\n"
        "**__CONCLUSION :__**\n**Carcinome, taille tumorale : 45 mm.**\n",
    ),
    (
        "C7",
        regle_c7_unites_homogenes,
        "Pièce mesurant 20 x 15 mm x 3 cm.",
    ),
    (
        "C8",
        regle_c8_trois_axes,
        "**Macroscopie :**\nPièce de mastectomie mesurant 120 x 90 mm.\n",
    ),
    (
        "C9",
        regle_c9_marges_presentes,
        "**Macroscopie :**\nPièce de tumorectomie.\n"
        "**Microscopie :**\nCarcinome infiltrant.\n",
    ),
    (
        "C10",
        regle_c10_lesion_conclue_decrite,
        "**Microscopie :**\nMuqueuse remaniée. Absence de signe de malignité.\n"
        "**__CONCLUSION :__**\n**Adénocarcinome infiltrant.**\n",
    ),
    (
        "C11",
        regle_c11_marqueur_conclu_documente,
        "**Microscopie :**\nProlifération épithéliale. CK7 positif.\n"
        "**__CONCLUSION :__**\n**Tumeur TTF1 positive.**\n",
    ),
    (
        "C12",
        regle_c12_negation_de_normalite,
        "Absence de cellule normale sur le frottis.",
    ),
    (
        "C12",
        regle_c12_negation_contredite,
        "Carcinome épidermoïde infiltrant, sans signe de malignité.",
    ),
    (
        "C13",
        regle_c13_lateralite,
        "**__MASTECTOMIE DROITE__**\n**Macroscopie :**\nPièce de mastectomie droite.\n"
        "**__CONCLUSION :__**\n**Carcinome du sein gauche.**\n",
    ),
    (
        "C14",
        regle_c14_organe,
        "**__BIOPSIE PROSTATIQUE__**\n**Macroscopie :**\nCarottes prostatiques.\n"
        "**__CONCLUSION :__**\n**Adénocarcinome de la thyroïde.**\n",
    ),
    (
        "C15",
        regle_c15_marges_mesurees,
        "**Macroscopie :**\nPièce de tumorectomie.\n"
        "**Microscopie :**\nCarcinome infiltrant. Limites d'exérèse saines.\n",
    ),
    (
        "C16",
        regle_c16_ganglions_examines,
        "**Macroscopie :**\nCurage axillaire adressé.\n"
        "**Microscopie :**\nAucun ganglion métastatique.\n",
    ),
    (
        "C16",
        regle_c16_ganglions_envahis,
        "**Macroscopie :**\nCurage axillaire : 12 ganglions examinés.\n",
    ),
]


@pytest.mark.parametrize(
    "regle_attendue,regle,texte",
    CAS_FAUTIFS,
    ids=[f"{r}-{f.__name__}" for r, f, _ in CAS_FAUTIFS],
)
def test_chaque_regle_se_declenche_sur_son_cas_fautif(regle_attendue, regle, texte):
    alerte = regle(texte)
    assert alerte is not None, f"{regle.__name__} n'a rien signale"
    assert alerte.regle == regle_attendue
    assert alerte.message.strip()


def test_toutes_les_regles_du_catalogue_sont_couvertes():
    # C1 a C16 sont testees ci-dessus ; C17 est declaree non evaluable.
    couvertes = {code for code, _, _ in CAS_FAUTIFS} | set(REGLES_NON_EVALUABLES)
    attendues = {f"C{n}" for n in range(1, 18)}
    assert couvertes == attendues


# ---------------------------------------------------------------------------
# Cas negatifs cibles : les gardes anti-faux-positif
# ---------------------------------------------------------------------------


def test_c1_ignore_une_numerotation_qui_ne_part_pas_de_un():
    # Blocs complementaires d'un dossier anterieur : la continuite est inverifiable.
    assert regle_c1_blocs_continus("Recoupes sur les blocs 4 et 6.") is None


def test_c1_accepte_un_meme_bloc_cite_dans_le_meme_prelevement():
    texte = "1) Tumeur, blocs 1 à 4. Le bloc 4 emporte la limite.\n2) Curage, blocs 5 à 8.\n"
    assert regle_c1_blocs_uniques(texte) is None


def test_c2_s_abstient_sans_section_numerotee():
    # Deux prelevements decrits en prose : rien a compter, donc rien a dire.
    assert regle_c2_nombre_de_prelevements("Deux prélèvements adressés.") is None


def test_c2_s_abstient_si_deux_annonces_divergent():
    texte = "Deux prélèvements.\nTrois prélèvements au total.\n1) A.\n2) B.\n"
    assert regle_c2_nombre_de_prelevements(texte) is None


def test_c2_utilise_la_dictee_en_repli():
    cr = "**Macroscopie :**\n1) Estomac.\n2) Duodénum.\n"
    assert regle_c2_nombre_de_prelevements(cr) is None
    alerte = regle_c2_nombre_de_prelevements(cr, "j'ai reçu trois prélèvements")
    assert alerte is not None and alerte.regle == "C2"
    assert "dictee" in alerte.message


def test_c3_s_abstient_sur_une_seule_station():
    texte = "Station 7 : 5 ganglions. Au total 12 ganglions examinés."
    assert regle_c3_somme_des_ganglions(texte) is None


def test_c3_s_abstient_si_une_station_est_comptee_deux_fois_differemment():
    texte = (
        "Station 7 : 5 ganglions ; station 4R : 3 ganglions.\n"
        "Station 7 : 6 ganglions. Au total 14 ganglions."
    )
    assert regle_c3_somme_des_ganglions(texte) is None


def test_c3_accepte_une_somme_juste():
    texte = "Station 4R : 5 ganglions ; station 7 : 6 ganglions. Au total 11 ganglions."
    assert regle_c3_somme_des_ganglions(texte) is None


def test_c4_accepte_zero_envahi():
    assert regle_c4_envahis_inferieur_examines("0 ganglion envahi sur 18 examinés.") is None


def test_c4_accepte_l_egalite():
    assert regle_c4_envahis_inferieur_examines("18 ganglions envahis sur 18 examinés.") is None


@pytest.mark.parametrize(
    "texte",
    [
        "12 ganglions examinés dont 3 métastatiques.",
        "3 ganglions métastatiques sur 12 examinés.",
        "pN1 (3/12)",
        "3/12 ganglions envahis.",
    ],
)
def test_c4_lit_les_formulations_usuelles(texte):
    # Formulations correctes : reconnues, donc silencieuses.
    assert regle_c4_envahis_inferieur_examines(texte) is None


def test_c4_signale_l_inversion_dans_chaque_formulation():
    assert regle_c4_envahis_inferieur_examines("pN1 (12/3)") is not None
    assert regle_c4_envahis_inferieur_examines("2 ganglions examinés dont 3 envahis.") is not None


def test_c5_s_abstient_si_la_section_donne_plusieurs_comptes():
    texte = (
        "**Macroscopie :**\nTrois fragments et deux fragments complémentaires.\n"
        "**Microscopie :**\nLes 2 fragments sont sains.\n"
    )
    assert regle_c5_fragments(texte) is None


def test_c6_accepte_une_taille_microscopique_inferieure():
    texte = (
        "**Macroscopie :**\nNodule de 30 x 25 x 20 mm.\n"
        "**__CONCLUSION :__**\n**Carcinome, taille tumorale : 12 mm.**\n"
    )
    assert regle_c6_taille_conclusion(texte) is None


def test_c6_accepte_une_taille_reprise_en_microscopie():
    texte = (
        "**Macroscopie :**\nNodule de 30 mm.\n"
        "**Microscopie :**\nLa lésion mesure 45 mm sur lame.\n"
        "**__CONCLUSION :__**\n**Carcinome, taille tumorale : 45 mm.**\n"
    )
    assert regle_c6_taille_conclusion(texte) is None


def test_c7_accepte_cm_pour_la_piece_et_mm_pour_la_lesion():
    # Usage standard en anatomie pathologique : ce n'est pas une incoherence.
    texte = "Pièce de 12 x 8 x 3 cm. Lésion de 18 mm de grand axe."
    assert regle_c7_unites_homogenes(texte) is None


def test_c8_accepte_deux_axes_avec_une_epaisseur_donnee():
    texte = "**Macroscopie :**\nPièce d'exérèse cutanée de 30 x 12 mm, épaisseur 8 mm.\n"
    assert regle_c8_trois_axes(texte) is None


def test_c8_ignore_une_lesion_mesuree_sur_deux_axes():
    texte = "**Macroscopie :**\nPlage indurée de 20 x 15 mm à la coupe.\n"
    assert regle_c8_trois_axes(texte) is None


def test_c9_ignore_une_biopsie():
    # Sans exerese, la question des limites ne se pose pas.
    texte = "**Macroscopie :**\nDeux carottes biopsiques.\n**Microscopie :**\nCarcinome.\n"
    assert regle_c9_marges_presentes(texte) is None


def test_c9_ignore_une_malignite_niee():
    texte = (
        "**Macroscopie :**\nPièce de tumorectomie.\n"
        "**Microscopie :**\nAbsence de carcinome. Lésion bénigne.\n"
    )
    assert regle_c9_marges_presentes(texte) is None


@pytest.mark.parametrize(
    "microscopie",
    [
        "Tumeur de Warthin (cystadénolymphome) parotidien.",
        "Dystrophie nodulaire bénigne. Absence d'élément suspect de malignité.",
        "Adénose sclérosante. On n'observe jamais les caractéristiques "
        "cytonucléaires des carcinomes papillaires.",
    ],
)
def test_c9_ne_prend_pas_une_lesion_benigne_pour_une_lesion_maligne(microscopie):
    # Pieges releves sur le corpus du praticien : elision de la negation
    # ("absence d'"), tournure "on n'observe jamais", et nom benin contenant
    # une racine maligne (cystadenoLYMPHOME).
    texte = f"**Macroscopie :**\nPièce d'exérèse.\n**Microscopie :**\n{microscopie}\n"
    assert regle_c9_marges_presentes(texte) is None


def test_c9_accepte_une_marge_qualitative_sans_le_mot_marge():
    texte = (
        "**Macroscopie :**\nPièce de polypectomie.\n"
        "**Microscopie :**\nAdénocarcinome intra-muqueux. L'exérèse de la lésion "
        "adénomateuse est incomplète.\n"
    )
    assert regle_c9_marges_presentes(texte) is None
    # Exerese incomplete = marge atteinte : la distance n'a plus d'objet.
    assert regle_c15_marges_mesurees(texte) is None


def test_c15_signale_une_exerese_dite_complete_sans_distance():
    texte = (
        "**Macroscopie :**\nPièce de polypectomie.\n"
        "**Microscopie :**\nAdénocarcinome intra-muqueux. L'exérèse est complète.\n"
    )
    alerte = regle_c15_marges_mesurees(texte)
    assert alerte is not None and alerte.regle == "C15"


def test_c14_ignore_la_locution_au_sein_de():
    # "au sein d'un tissu" ne designe pas la glande mammaire.
    texte = (
        "**__BIOPSIE DE GLANDE SALIVAIRE ACCESSOIRE__**\n"
        "**Macroscopie :**\nTrois fragments muqueux.\n"
        "**__CONCLUSION :__**\n**Au sein d'un tissu fibro-inflammatoire, "
        "lésions granulomateuses du parenchyme salivaire.**\n"
    )
    assert regle_c14_organe(texte) is None


def test_c10_accepte_une_conclusion_qui_nomme_ce_que_la_microscopie_decrit():
    # Une conclusion NOMME l'entite que la microscopie DECRIT : ce n'est pas une
    # incoherence, c'est son role. Seule la contradiction franche est signalee.
    texte = (
        "**Microscopie :**\nAdossements glandulaires cribriformes, mitoses nombreuses.\n"
        "**__CONCLUSION :__**\n**Adénocarcinome intra-muqueux.**\n"
    )
    assert regle_c10_lesion_conclue_decrite(texte) is None


def test_c10_ignore_une_malignite_niee_dans_la_conclusion():
    texte = (
        "**Microscopie :**\nMuqueuse remaniée. Absence de signe de malignité.\n"
        "**__CONCLUSION :__**\n**Absence de carcinome infiltrant.**\n"
    )
    assert regle_c10_lesion_conclue_decrite(texte) is None


def test_c11_s_abstient_si_le_cr_ne_documente_aucune_ihc():
    # Sans tableau IHC dans le document, il n'y a rien a confronter.
    texte = (
        "**Microscopie :**\nProlifération épithéliale.\n"
        "**__CONCLUSION :__**\n**Tumeur TTF1 positive.**\n"
    )
    assert regle_c11_marqueur_conclu_documente(texte) is None


def test_c11_accepte_un_marqueur_documente_en_immunohistochimie():
    texte = (
        "**Microscopie :**\nProlifération.\n"
        "**Immunohistochimie :**\nTTF1 positif.\n"
        "**__CONCLUSION :__**\n**Tumeur TTF1 positive.**\n"
    )
    assert regle_c11_marqueur_conclu_documente(texte) is None


@pytest.mark.parametrize(
    "texte",
    [
        "Absence de cellule anormale.",
        "Pas de signe de malignité.",
        "Absence de parenchyme sain résiduel.",
        "Muqueuse sans particularité.",
    ],
)
def test_c12_ne_touche_pas_aux_negations_correctes(texte):
    assert regle_c12_negation_de_normalite(texte) is None


def test_c12_ne_confronte_pas_deux_phrases_distinctes():
    # Multi-prelevement : une tumeur ici, un ganglion indemne la, c'est normal.
    texte = "Carcinome canalaire infiltrant. Absence de malignité sur le ganglion sentinelle."
    assert regle_c12_negation_contredite(texte) is None


def test_c13_ignore_un_cr_bilateral():
    texte = (
        "**__BIOPSIES BILATERALES__**\n**Macroscopie :**\nSein droit et sein gauche.\n"
        "**__CONCLUSION :__**\n**Sein droit : carcinome. Sein gauche : lésion bénigne.**\n"
    )
    assert regle_c13_lateralite(texte) is None


def test_c13_ignore_une_section_sans_lateralite():
    texte = (
        "**__MASTECTOMIE DROITE__**\n**Macroscopie :**\nPièce de mastectomie.\n"
        "**__CONCLUSION :__**\n**Carcinome infiltrant du sein droit.**\n"
    )
    assert regle_c13_lateralite(texte) is None


def test_c14_accepte_un_tissu_voisin_nomme_en_conclusion():
    # La conclusion nomme la lesion et peut citer un tissu voisin : ce n'est
    # fautif que si l'organe n'apparait nulle part ailleurs.
    texte = (
        "**__BIOPSIE OESOPHAGIENNE__**\n"
        "**Macroscopie :**\nDeux fragments de muqueuse œsophagienne.\n"
        "**Microscopie :**\nMuqueuse œsophagienne avec métaplasie gastrique.\n"
        "**__CONCLUSION :__**\n**Métaplasie gastrique.**\n"
    )
    assert regle_c14_organe(texte) is None


def test_c14_ignore_les_familles_lesionnelles():
    # "lipome" ne fait pas du colon un sarcome : les familles lesionnelles ne
    # sont pas des organes et ne doivent pas creer de divergence.
    texte = (
        "**__COLECTOMIE__**\n**Macroscopie :**\nPièce de colectomie.\n"
        "**__CONCLUSION :__**\n**Lipome sous-muqueux colique.**\n"
    )
    assert regle_c14_organe(texte) is None


def test_c14_accepte_un_organe_commun_parmi_plusieurs():
    texte = (
        "**__LOBECTOMIE PULMONAIRE ET CURAGE__**\n"
        "**Macroscopie :**\nPièce de lobectomie pulmonaire.\n"
        "**__CONCLUSION :__**\n**Adénocarcinome pulmonaire, ganglions métastatiques.**\n"
    )
    assert regle_c14_organe(texte) is None


def test_c15_accepte_une_marge_atteinte_sans_distance():
    # Marge atteinte : la distance n'a plus d'objet.
    texte = (
        "**Macroscopie :**\nPièce de tumorectomie.\n"
        "**Microscopie :**\nCarcinome infiltrant. Limite d'exérèse profonde atteinte.\n"
    )
    assert regle_c15_marges_mesurees(texte) is None


def test_c16_accepte_une_absence_d_envahissement_non_chiffree():
    texte = (
        "**Macroscopie :**\nCurage axillaire : 12 ganglions examinés.\n"
        "**Microscopie :**\nSans métastase ganglionnaire.\n"
    )
    assert regle_c16_ganglions_envahis(texte) is None


def test_c16_ignore_un_cr_sans_curage():
    texte = "**Macroscopie :**\nBiopsie bronchique.\n**Microscopie :**\nAdénocarcinome.\n"
    assert regle_c16_ganglions_examines(texte) is None
    assert regle_c16_ganglions_envahis(texte) is None


# ---------------------------------------------------------------------------
# Decoupage, empans et point d'entree
# ---------------------------------------------------------------------------


def test_decoupage_reconnait_les_sections_titrees():
    sections = decouper_sections(CR_SEIN)
    assert sorted(sections) == ["conclusion", "macroscopie", "microscopie", "titre"]
    assert sections["titre"].texte == "PIECE DE TUMORECTOMIE DU SEIN DROIT"
    assert "tumorectomie orientée" in sections["macroscopie"].texte
    assert "grade SBR 2" in sections["conclusion"].texte


def test_decoupage_concatene_les_sections_repetees():
    cr = (
        "**Macroscopie :**\nPremier pot.\n**Microscopie :**\nA.\n"
        "**Macroscopie :**\nSecond pot.\n**Microscopie :**\nB.\n"
    )
    macro = decouper_sections(cr)["macroscopie"].texte
    assert "Premier pot." in macro and "Second pot." in macro


def test_le_gras_de_la_conclusion_ne_coupe_pas_la_section():
    cr = "**__CONCLUSION :__**\n**Adénocarcinome infiltrant.**\n"
    assert "Adénocarcinome" in decouper_sections(cr)["conclusion"].texte


def test_l_empan_pointe_le_texte_incrimine():
    alerte = regle_c4_envahis_inferieur_examines("Bilan : 3 ganglions envahis sur 2 examinés.")
    assert alerte is not None and alerte.empan is not None
    debut, fin = alerte.empan.debut, alerte.empan.fin
    assert "Bilan : 3 ganglions envahis sur 2 examinés."[debut:fin] == alerte.empan.texte
    assert "3" in alerte.empan.texte


def test_alerte_serialisable():
    alerte = AlerteDocument("C4", "message", None)
    assert alerte.to_dict() == {"regle": "C4", "message": "message", "empan": None}


def test_point_d_entree_agrege_plusieurs_alertes():
    cr = (
        "**__MASTECTOMIE DROITE__**\n"
        "**Macroscopie :**\nPièce de mastectomie mesurant 120 x 90 mm. "
        "Inclusion en blocs 1, 2 et 4.\n"
        "**Microscopie :**\nCarcinome infiltrant. Limites d'exérèse saines. "
        "3 ganglions métastatiques sur 2 examinés.\n"
        "**__CONCLUSION :__**\n**Carcinome infiltrant du sein gauche.**\n"
    )
    codes = {a.regle for a in verifier_coherence_document(cr)}
    assert {"C1", "C4", "C8", "C13", "C15"} <= codes


def test_point_d_entree_muet_sur_un_texte_vide_ou_un_refus():
    assert verifier_coherence_document("") == []
    assert verifier_coherence_document("Cette dictée ne semble pas correspondre à un CR.") == []


def test_c17_est_expose_comme_non_evaluable():
    assert "C17" in REGLES_NON_EVALUABLES
    assert "referentiel" in REGLES_NON_EVALUABLES["C17"]
