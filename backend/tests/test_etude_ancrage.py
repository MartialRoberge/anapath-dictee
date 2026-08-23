"""Ancrage d'une proposition dans le verbatim.

Ces tests protegent la regle fondatrice de l'etude — pas d'empan, pas de
proposition — et le seul defaut qui serait pire que l'absence d'empan : un
empan decale, qui ferait valider un mot pour un autre.
"""

from etude.ancrage import (
    SEUIL_RECOUVREMENT,
    Empan,
    ancrer,
    decouper,
    est_copie_litterale,
    jetons_discriminants,
)

VERBATIM = (
    "Alors, biopsie du colon sigmoide chez un patient de soixante-deux ans. "
    "Macroscopiquement on a trois fragments brunatres mesurant de deux a "
    "quatre millimetres. A l'examen histologique, il s'agit d'une "
    "proliferation glandulaire atypique, avec des noyaux allonges "
    "pseudostratifies limites a la moitie basale de l'epithelium. "
    "Pas de franchissement de la musculaire muqueuse. "
    "Les limites de resection sont saines."
)


def test_les_offsets_pointent_vers_le_texte_d_origine():
    """Le piege : normaliser avant de reperer les positions. 'oesophage'
    remplace 'oesophage' et gagne un caractere, donc tous les empans suivants
    se decalent et surlignent le mot d'a cote."""
    texte = "L'œsophage est le siege d'une metaplasie intestinale."
    jetons = decouper(texte)
    for jeton in jetons:
        # Chaque jeton doit se retrouver a sa position dans le texte d'origine.
        assert len(texte[jeton.debut:jeton.fin]) == jeton.fin - jeton.debut
    formes = [j.forme for j in jetons]
    assert "oesophage" in formes
    oesophage = next(j for j in jetons if j.forme == "oesophage")
    assert texte[oesophage.debut:oesophage.fin] == "œsophage"


def test_une_reformulation_est_ancree():
    """Le compte rendu reformule ; l'ancrage doit resister a la reformulation,
    sinon il ne servirait qu'aux copies mot pour mot, qui ne se valident pas."""
    empan = ancrer(
        "Noyaux allonges et pseudostratifies confines a la moitie basale",
        VERBATIM,
    )
    assert empan is not None
    assert "pseudostratifies" in empan.extrait
    assert "moitie basale" in empan.extrait


def test_l_empan_est_serre_et_pas_le_verbatim_entier():
    """Un empan qui couvre toute la dictee ne designe rien : le praticien
    devrait tout relire, et il validerait par lassitude."""
    empan = ancrer("Limites de resection saines", VERBATIM)
    assert empan is not None
    assert len(empan.extrait) < len(VERBATIM) / 3
    assert "resection" in empan.extrait


def test_une_assertion_absente_de_la_dictee_n_est_pas_ancree():
    """C'est le cas qui compte : une hallucination ne doit pas recevoir
    d'empan de complaisance. Sans empan, elle n'est pas affichable."""
    assert ancrer("Emboles vasculaires et engainements perinerveux", VERBATIM) is None


def test_un_fragment_trop_pauvre_n_est_pas_ancre():
    """'Elle est presente' se retrouverait n'importe ou : deux jetons
    discriminants au minimum."""
    assert ancrer("Elle est presente", VERBATIM) is None
    assert ancrer("", VERBATIM) is None


def test_verbatim_vide():
    assert ancrer("Adenocarcinome lieberkuhnien", "") is None


def test_les_mots_vides_ne_gonflent_pas_le_recouvrement():
    """Sinon un fragment fait de 'de la du et' atteindrait le seuil sans
    partager le moindre terme medical avec la dictee."""
    assert jetons_discriminants("de la du et avec dans sur") == []


def test_les_chiffres_n_entrent_pas_au_denominateur():
    """La dictee dit 'deux a quatre millimetres', le compte rendu ecrit
    '2 a 4 mm'. Exiger la correspondance chiffree rejetterait l'ancrage."""
    empan = ancrer("Trois fragments brunatres mesurant 2 a 4 mm", VERBATIM)
    assert empan is not None
    assert "fragments" in empan.extrait


def test_copie_litterale_reconnue():
    """Cahier de recueil : une copie litterale est une transcription, pas une
    proposition. La compter gonflerait le taux d'acceptation avec des
    evidences que personne n'a eu a juger."""
    assert est_copie_litterale("les limites de resection sont saines", VERBATIM)


def test_une_inference_n_est_pas_une_copie_litterale():
    """Ce diagnostic n'est prononce nulle part : c'est l'inference du moteur,
    et c'est exactement ce qui doit se valider."""
    assert not est_copie_litterale(
        "Adenome tubuleux en dysplasie de bas grade", VERBATIM
    )


def test_meme_mots_ordre_different_n_est_pas_une_copie():
    """Une conclusion qui reassemble des mots dictes a des endroits differents
    est une synthese : elle se valide."""
    assert not est_copie_litterale(
        "resection saine du colon sigmoide sans franchissement", VERBATIM
    )


def test_une_inference_diagnostique_est_ancree_malgre_un_taux_bas():
    """Une conclusion INTRODUIT des mots absents de la dictee : son taux de
    recouvrement est structurellement bas. Si le taux seul decidait, l'etude
    perdrait justement les propositions qui comptent le plus."""
    empan = ancrer(
        "Adenome tubuleux en dysplasie de bas grade, developpe sur la muqueuse "
        "sigmoide, respectant la musculaire muqueuse sans franchissement",
        VERBATIM,
    )
    assert empan is not None
    assert empan.recouvrement < SEUIL_RECOUVREMENT


def test_une_proposition_fausse_mais_sur_le_sujet_reste_ancree():
    """La dictee dit l'inverse : 'pas de franchissement'. Cette proposition
    doit tout de meme etre ancree et affichee, car l'empan dit OU REGARDER, il
    ne prejuge pas de la justesse. C'est en la rejetant que le praticien
    produit la mesure ; une proposition filtree en amont ne se mesure pas."""
    assert ancrer(
        "Adenocarcinome infiltrant franchissant la musculaire muqueuse "
        "du sigmoide, avec emboles",
        VERBATIM,
    ) is not None


def test_le_recouvrement_est_trace():
    """Au depouillement, il faut pouvoir separer un ancrage franc d'un ancrage
    limite : le score fait partie de la donnee."""
    empan = ancrer("Proliferation glandulaire atypique", VERBATIM)
    assert isinstance(empan, Empan)
    assert 0.0 < empan.recouvrement <= 1.0


def test_l_ancrage_est_reproductible():
    """Condition pour publier : deux executions donnent le meme empan."""
    fragment = "Noyaux allonges pseudostratifies"
    assert ancrer(fragment, VERBATIM) == ancrer(fragment, VERBATIM)
