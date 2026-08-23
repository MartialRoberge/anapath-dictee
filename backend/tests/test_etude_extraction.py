"""Decoupage d'un compte rendu en propositions validables.

Chaque test protege un chiffre publie : ce qui entre au denominateur du taux
d'acceptation, ce qui n'y entre pas, et ce qui n'est jamais affiche.
"""

from etude.extraction import (
    BUDGET_MAX,
    extraire,
    extraire_codes,
    extraire_completudes,
    extraire_restitutions,
    sous_extraction,
)
from etude.vocabulaire import TYPE_CODE, TYPE_COMPLETUDE, TYPE_RESTITUTION

VERBATIM = (
    "Alors biopsies etagees du colon sigmoide chez un homme de soixante-deux ans. "
    "Macroscopiquement trois fragments brunatres de deux a quatre millimetres. "
    "A l'histologie on voit une proliferation glandulaire avec des noyaux "
    "allonges pseudostratifies limites a la moitie basale de l'epithelium, "
    "sans franchissement de la musculaire muqueuse. "
    "Les limites de resection sont saines. "
    "Il n'y a pas de signe de malignite."
)

CR = """**Examen anatomo-pathologique**

**Renseignements cliniques :**
Homme de 62 ans, biopsies etagees du colon sigmoide.

**Macroscopie :**
Trois fragments brunatres mesurant de 2 a 4 mm.

**Microscopie :**
- Proliferation glandulaire faite de noyaux allonges et pseudostratifies confines a la moitie basale de l'epithelium.
- Absence de franchissement de la musculaire muqueuse.
- Les limites de resection sont saines.
- Le grade nucleaire est [A COMPLETER].

**Conclusion :**
Adenome tubuleux en dysplasie de bas grade du colon sigmoide, sans signe de malignite.
"""


def test_une_copie_litterale_n_est_pas_une_proposition():
    """Cahier §7 : la copie litterale est une transcription. La compter
    gonflerait le taux d'acceptation avec des evidences non jugees."""
    valeurs = [p.valeur_proposee for p in extraire_restitutions(CR, VERBATIM)]
    assert not any("limites de resection sont saines" in v.lower() for v in valeurs)


def test_l_inference_diagnostique_est_une_proposition():
    """Le diagnostic n'est prononce nulle part dans la dictee : c'est
    exactement ce que le praticien doit juger."""
    valeurs = [p.valeur_proposee for p in extraire_restitutions(CR, VERBATIM)]
    assert any("adenome tubuleux" in v.lower() for v in valeurs)


def test_un_champ_a_completer_n_est_pas_une_restitution():
    """[A COMPLETER] est un aveu d'absence, pas une affirmation du moteur.
    Le juger comme une restitution serait un contresens."""
    valeurs = [p.valeur_proposee for p in extraire_restitutions(CR, VERBATIM)]
    assert not any("[A COMPLETER]" in v for v in valeurs)


def test_une_proposition_ancree_porte_un_empan_utilisable():
    """Quand l'empan existe, il doit designer quelque chose : un empan vide
    afficherait un surlignage de zero caractere, donc un mensonge visuel."""
    for proposition in extraire_restitutions(CR, VERBATIM):
        if not proposition.ancree:
            assert proposition.empan_debut is None
            continue
        assert proposition.empan_fin > proposition.empan_debut
        assert proposition.empan_extrait


def test_l_empan_pointe_bien_dans_le_verbatim():
    """Un empan decale ferait valider un mot pour un autre."""
    for proposition in extraire_restitutions(CR, VERBATIM):
        if not proposition.ancree:
            continue
        extrait = VERBATIM[proposition.empan_debut:proposition.empan_fin]
        assert extrait == proposition.empan_extrait


def test_la_conclusion_passe_avant_la_macroscopie():
    """A budget serre, c'est ce qui engage le diagnostic qu'on garde."""
    sections = [p.sous_type for p in extraire_restitutions(CR, VERBATIM)]
    if "conclusion" in sections and "macroscopie" in sections:
        assert sections.index("conclusion") < sections.index("macroscopie")


def test_les_titres_ne_deviennent_pas_des_propositions():
    valeurs = [p.valeur_proposee for p in extraire_restitutions(CR, VERBATIM)]
    assert "Examen anatomo-pathologique" not in valeurs
    assert "Microscopie" not in valeurs


def test_un_code_non_ancre_n_est_pas_affiche():
    """Un code declenche par un terme absent de la dictee est invalidable :
    le praticien ne saurait pas sur quoi le juger."""
    codes = [
        {"code": "BHGS0030", "libelle": "Colon sigmoide", "position": "D3",
         "declencheur": "colon sigmoide"},
        {"code": "ZZZZ9999", "libelle": "Prostate", "position": "D3",
         "declencheur": "prostate adenocarcinome acineux"},
    ]
    resultat = extraire_codes(codes, VERBATIM)
    assert [p.valeur_proposee for p in resultat] == ["BHGS0030"]
    assert resultat[0].type_proposition == TYPE_CODE


def test_chaque_code_est_une_proposition_distincte():
    """Un code juste et un code faux doivent produire deux mesures, jamais
    une moyenne : c'est la cardinalite qui rend l'exactitude publiable."""
    codes = [
        {"code": "BHGS0030", "libelle": "Colon", "position": "D3",
         "declencheur": "colon sigmoide"},
        {"code": "H", "libelle": "Histologie", "position": "D2",
         "declencheur": "biopsies etagees colon"},
    ]
    assert len(extraire_codes(codes, VERBATIM)) == 2


def test_une_completude_survit_sans_ancrage():
    """Une suggestion de completude constate une ABSENCE : elle n'affirme rien
    sur la dictee, donc l'absence d'empan ne la disqualifie pas."""
    alertes = [{"champ": "grade", "description": "Grade histopronostique",
                "section": "conclusion"}]
    resultat = extraire_completudes(alertes, VERBATIM)
    assert len(resultat) == 1
    assert resultat[0].type_proposition == TYPE_COMPLETUDE
    assert resultat[0].empan_debut is None
    assert not resultat[0].ancree


def test_le_budget_est_respecte():
    """Au-dela, le praticien clique sans lire et l'on mesure sa fatigue."""
    cr_long = CR + "\n".join(
        f"- Constatation numero {i} sur les noyaux allonges pseudostratifies."
        for i in range(60)
    )
    assert len(extraire(cr_long, VERBATIM)) <= BUDGET_MAX


def test_codes_et_completudes_passent_avant_les_restitutions():
    """Ce sont les mesures les plus dures de l'etude : les perdre au profit
    d'une dixieme phrase de microscopie appauvrirait le depouillement."""
    codes = [{"code": "BHGS0030", "libelle": "Colon", "position": "D3",
              "declencheur": "colon sigmoide"}]
    alertes = [{"champ": "grade", "description": "Grade histopronostique",
                "section": "conclusion"}]
    resultat = extraire(CR, VERBATIM, codes=codes, alertes=alertes, budget=2)
    types = {p.type_proposition for p in resultat}
    assert types == {TYPE_CODE, TYPE_COMPLETUDE}
    assert TYPE_RESTITUTION not in types


def test_la_longueur_en_mots_est_calculee():
    """Elle sert au marquage `hative` : sans elle, on ne sait pas distinguer
    une decision rapide legitime d'un clic sans lecture."""
    for proposition in extraire_restitutions(CR, VERBATIM):
        assert proposition.longueur_mots == len(proposition.valeur_proposee.split())


def test_sous_extraction_signalee():
    """Un CR qui ne produit presque rien a valider n'apporte rien a l'etude :
    il faut le savoir, pas le decouvrir au depouillement."""
    assert sous_extraction([])
    assert not sous_extraction(list(range(8)))  # type: ignore[arg-type]


def test_un_verbatim_vide_rend_tout_non_ancre():
    """Un compte rendu produit a partir de rien est entierement halluciné.
    Le dire est plus utile que de ne rien renvoyer."""
    propositions = extraire_restitutions(CR, "")
    assert propositions
    assert all(not p.ancree for p in propositions)
    assert all(p.empan_debut is None for p in propositions)


# --- Les candidates hallucinations -----------------------------------------


def test_une_assertion_sans_appui_est_conservee_et_marquee():
    """Mesure sur cas reels : supprimer ces propositions faisait disparaitre
    "absence de metastase ganglionnaire", "la bronche et les vaisseaux sont
    sains" — exactement les affirmations qu'une hallucination rendrait
    dangereuses. C'est la mesure centrale de l'etude, elle ne se jette pas."""
    cr = CR + "\n\n**Immunohistochimie :**\nLe marquage p53 est nul, en faveur d'une mutation.\n"
    propositions = extraire_restitutions(cr, VERBATIM)
    fantome = [p for p in propositions if "p53" in p.valeur_proposee]
    assert fantome, "l'assertion non dictee a ete supprimee"
    assert not fantome[0].ancree
    assert fantome[0].empan_debut is None


def test_une_candidate_hallucination_passe_devant():
    """Elle est la plus precieuse de l'etude : elle ne doit pas tomber hors
    budget derriere une dixieme phrase de macroscopie."""
    cr = CR + "\n\n**Immunohistochimie :**\nLe marquage p53 est nul, en faveur d'une mutation.\n"
    propositions = extraire_restitutions(cr, VERBATIM)
    assert not propositions[0].ancree


def test_un_commentaire_de_machine_n_est_pas_une_proposition():
    """Le moteur qui s'adresse a lui-meme n'affirme rien sur le cas : le faire
    juger ferait perdre une decision et brouillerait le taux d'hallucination."""
    cr = CR + '\n\nNote : [VERIFIER: "sept bareties" — terme incompris]\n'
    valeurs = [p.valeur_proposee for p in extraire_restitutions(cr, VERBATIM)]
    assert not any("VERIFIER" in v for v in valeurs)


def test_un_gabarit_conditionnel_n_est_pas_une_proposition():
    cr = CR + "\n\nPanel standard pour adenocarcinome pulmonaire (TTF1, CK7) si realise.\n"
    valeurs = [p.valeur_proposee for p in extraire_restitutions(cr, VERBATIM)]
    assert not any("Panel standard" in v for v in valeurs)


def test_une_etiquette_de_bloc_n_est_pas_une_proposition():
    """"Tumeur : blocs 11 a 13" organise le document, elle n'affirme rien."""
    cr = CR + "\n\nTumeur : blocs 11 a 13\n"
    valeurs = [p.valeur_proposee for p in extraire_restitutions(cr, VERBATIM)]
    assert not any("blocs 11" in v for v in valeurs)
