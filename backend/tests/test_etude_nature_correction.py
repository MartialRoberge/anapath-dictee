"""Nature d'une correction : le systeme s'est-il trompe, ou j'ecris autrement ?

Sans cette separation, toute correction compte comme un echec du systeme et le
taux publie melange deux choses sans rapport. Ces tests defendent la frontiere.
"""

from etude.nature_correction import (
    IDENTIQUE,
    PRECISION,
    STYLE,
    SUBSTANCE,
    classer,
    declaration_coherente,
    retouches_silencieuses,
)


# --- Ce qui n'impute PAS d'erreur au systeme -------------------------------


def test_une_reformulation_est_du_style():
    """Memes termes, memes chiffres, meme polarite : le fond tenait. Compter
    ceci comme une erreur ferait passer un outil juste pour un outil faux."""
    ecart = classer(
        "La biopsie montre une proliferation glandulaire atypique",
        "Proliferation glandulaire atypique sur la biopsie",
    )
    assert ecart.nature == STYLE
    assert not ecart.chiffres_modifies


def test_un_ajout_de_precision_n_est_pas_une_erreur():
    """Le systeme n'avait pas tort, il n'en savait pas assez : succes partiel,
    pas echec."""
    ecart = classer(
        "Adenocarcinome du colon",
        "Adenocarcinome lieberkuhnien moyennement differencie du colon",
    )
    assert ecart.nature == PRECISION
    assert "lieberkuhnien" in ecart.termes_ajoutes
    assert ecart.termes_retires == ()


def test_un_texte_inchange_est_identique():
    assert classer("Limites saines", "Limites saines").nature == IDENTIQUE


# --- Ce qui touche au fond -------------------------------------------------


def test_un_chiffre_modifie_tranche_seul():
    """4,5 cm devenu 5,2 cm est une correction de fond, quelle que soit la part
    de caracteres touches — un seul caractere suffit a changer une mesure."""
    ecart = classer("La tumeur mesure 4,5 cm", "La tumeur mesure 5,2 cm")
    assert ecart.nature == SUBSTANCE
    assert ecart.chiffres_modifies


def test_une_negation_renversee_tranche_seule():
    """Le changement le plus grave qu'un diff puisse porter, et le plus facile
    a manquer a l'oeil : deux caracteres retournent le sens."""
    ecart = classer(
        "Presence de franchissement de la musculaire muqueuse",
        "Pas de franchissement de la musculaire muqueuse",
    )
    assert ecart.nature == SUBSTANCE
    assert ecart.negation_modifiee


def test_un_terme_retire_est_de_la_substance():
    """Le systeme avait affirme quelque chose que le praticien retire."""
    ecart = classer(
        "Adenocarcinome infiltrant avec emboles vasculaires",
        "Adenocarcinome infiltrant",
    )
    assert ecart.nature == SUBSTANCE
    assert "emboles" in ecart.termes_retires


def test_le_calcul_n_impute_jamais_une_erreur():
    """Un chiffre change peut etre une hallucination du systeme comme une
    relecture de la lame. Le calcul dit que le contenu a bouge ; il ne dit
    jamais que le systeme avait tort — cette imputation appartient au praticien."""
    ecart = classer("La tumeur mesure 4,5 cm", "La tumeur mesure 5,2 cm")
    assert ecart.nature == SUBSTANCE
    assert ecart.nature != "erreur_fond"


# --- Le croisement declare / calcule ---------------------------------------


def test_une_correction_de_style_qui_change_un_chiffre_est_incoherente():
    """C'est le garde-fou sur la declaration elle-meme : un praticien indulgent
    ou presse cocherait 'style' partout, et le taux d'erreur s'effondrerait
    sans que rien ne le signale."""
    ecart = classer("Trois fragments", "Quatre fragments de 5 mm")
    assert not declaration_coherente("style", ecart.nature)


def test_une_correction_de_style_sur_une_reformulation_est_coherente():
    ecart = classer("La biopsie montre une lesion", "Lesion vue sur la biopsie")
    assert declaration_coherente("style", ecart.nature)


def test_une_erreur_de_fond_declaree_est_toujours_recevable():
    """Le praticien peut savoir que le systeme avait tort la ou le texte bouge
    a peine : sa declaration prime sur le calcul dans ce sens-la."""
    ecart = classer("Lesion benigne", "Lesion maligne")
    assert declaration_coherente("erreur_fond", ecart.nature)


def test_une_nature_non_declaree_ne_fabrique_pas_d_incoherence():
    ecart = classer("Trois fragments", "Quatre fragments")
    assert declaration_coherente(None, ecart.nature)


# --- Le point aveugle : ce qui est corrige sans passer par un bouton -------


def test_une_retouche_hors_proposition_est_retrouvee():
    """C'est le point aveugle de l'instrumentation : ce que le praticien
    reecrit directement dans le texte ne passe par aucun bouton. Or c'est la
    que se cachent les erreurs sur lesquelles on ne l'a pas interroge."""
    propose = (
        "**Macroscopie :**\nTrois fragments de 4 mm.\n\n"
        "**Conclusion :**\nAdenome tubuleux en dysplasie de bas grade."
    )
    retenu = (
        "**Macroscopie :**\nTrois fragments de 4 mm.\n\n"
        "**Conclusion :**\nAdenome tubuleux en dysplasie de haut grade."
    )
    retouches = retouches_silencieuses(propose, retenu)
    assert len(retouches) == 1
    assert retouches[0].ecart.nature == SUBSTANCE


def test_un_compte_rendu_accepte_tel_quel_ne_produit_aucune_retouche():
    texte = "**Conclusion :**\nAdenome tubuleux."
    assert retouches_silencieuses(texte, texte) == []


def test_la_ponctuation_seule_ne_produit_pas_de_retouche():
    """Sinon les vraies retouches se noieraient dans le bruit typographique."""
    assert retouches_silencieuses("Lesion.", "Lesion. ") == []


def test_l_ampleur_permet_de_trier_les_corrections():
    """Au depouillement, une reecriture totale et une virgule deplacee ne se
    lisent pas de la meme facon."""
    petite = classer("Lesion benigne du colon", "Lesion benigne du colon.")
    grande = classer("Lesion benigne du colon", "Carcinome epidermoide du poumon")
    assert petite.ampleur < grande.ampleur
