"""Negation : ce qui doit disparaitre du codage, et ce qui doit y rester.

Deux familles de defauts, opposees, et les deux sont dangereuses :

  SOUS-MASQUAGE  une lesion NIEE recoit un code -> on affirme un cancer absent
  SUR-MASQUAGE   une lesion AFFIRMEE perd son code -> on manque un cancer present

Deux reecritures par portee ont echoue sur la seconde. Les cas qui les ont fait
tomber sont tous ici : ils tiennent lieu de memoire.
"""

import pytest

from negation import DECLENCHEURS, est_nie, mask_negations
from text_utils import normaliser


def _reste(phrase: str) -> str:
    """Ce qui survit au masquage, en texte normalise."""
    return mask_negations(normaliser(phrase))


def _masque(phrase: str, terme: str) -> bool:
    return normaliser(terme) not in _reste(phrase)


# --- SOUS-MASQUAGE : une lesion niee ne doit pas etre codee ----------------


@pytest.mark.parametrize(
    "phrase,terme",
    [
        ("Absence de metastase ganglionnaire.", "metastase"),
        # Les quatre suivantes echappaient au masque d'origine, qui ne
        # connaissait que la forme NON ELIDEE "absence de".
        ("Absence d'embole vasculaire.", "embole"),
        ("Absence d'adenocarcinome residuel.", "adenocarcinome"),
        ("Aucun signe de malignite.", "malignite"),
        ("On n'observe pas d'infiltration tumorale.", "infiltration"),
        # Apostrophe typographique : un CR colle depuis un traitement de texte
        # en est plein, et n'en traiter qu'une forme laisse passer l'autre.
        ("Absence d’adenocarcinome residuel.", "adenocarcinome"),
        # Dictee vocale : l'elision n'est pas transcrite.
        ("absence d adenocarcinome residuel", "adenocarcinome"),
        # Enumeration : la virgule ne doit pas refermer la negation quand la
        # suite enchaine par une preposition.
        ("Il n'y a pas de dysplasie, d'atypie ni de mitose.", "mitose"),
        ("Muqueuse depourvue de dysplasie.", "dysplasie"),
        ("Prelevement indemne de carcinome.", "carcinome"),
        ("Cytologie negative pour le carcinome urothelial.", "carcinome"),
        ("Cet aspect exclut un adenocarcinome gastrique.", "adenocarcinome"),
        ("Rien en faveur d'un adenocarcinome.", "adenocarcinome"),
        # Negation post-posee : toute la CR synoptique des checklists.
        ("Emboles vasculaires : non", "emboles"),
        ("Engainements perinerveux : absents", "engainements"),
    ],
)
def test_une_lesion_niee_disparait(phrase: str, terme: str):
    assert _masque(phrase, terme), f"{terme!r} reste codable dans {phrase!r}"


# --- SUR-MASQUAGE : une lesion affirmee doit survivre ---------------------


@pytest.mark.parametrize(
    "phrase,terme",
    [
        # LE cas qui a fait tomber les deux reecritures precedentes : la lesion
        # affirmee suit la negation DANS LA MEME PROPOSITION.
        ("Pas d'atypie cytonucleaire associee a une hyperplasie glandulaire.",
         "hyperplasie"),
        ("Ni granulome ni necrose, au contraire une hyperplasie lymphoide.",
         "hyperplasie"),
        ("Absence de dysplasie, en revanche adenocarcinome infiltrant.",
         "adenocarcinome"),
        ("Sans effraction capsulaire, avec engainements perinerveux.",
         "engainements"),
        ("Absence de metastase mais presence d'emboles vasculaires.", "emboles"),
        # Une virgule qui n'enchaine pas ferme la negation : ce qui suit est une
        # affirmation nouvelle, pas la suite de l'enumeration.
        ("Aucun ganglion metastatique sur 14 preleves, adenocarcinome differencie.",
         "adenocarcinome"),
        # "sans doute" RENFORCE une affirmation. Le lire comme une negation
        # effacait le diagnostic.
        ("Il s'agit sans doute d'un carcinome epidermoide infiltrant.", "carcinome"),
        # "non specifique" et "non compliquee" font partie du DIAGNOSTIC.
        ("Legere colite chronique non specifique.", "specifique"),
        ("Appendicite aigue non compliquee.", "compliquee"),
        # Un declencheur ne doit pas matcher au milieu d'un mot : ces deux
        # descriptions reelles du corpus etaient effacees.
        ("Acini de la glande de bartholin.", "bartholin"),
        ("Le calibre des glandes est regulier.", "glandes"),
        # La coloration PAS n'est pas une negation.
        ("La coloration PAS met en evidence des mucines.", "coloration"),
        # Au-dela de la fenetre, un terme est hors d'atteinte par construction.
        ("Pas de dysplasie. La piece montre un adenocarcinome infiltrant.",
         "adenocarcinome"),
    ],
)
def test_une_lesion_affirmee_survit(phrase: str, terme: str):
    reste = _reste(phrase)
    assert normaliser(terme) in reste, (
        f"{terme!r} a ete efface de {phrase!r} — reste : {reste.strip()!r}"
    )


# --- Proprietes du masque -------------------------------------------------


def test_les_positions_sont_conservees():
    """Des appelants comparent des positions entre le texte d'origine et le
    texte masque : un masque qui raccourcit le texte les decalerait tous."""
    texte = normaliser("Adenocarcinome du colon. Absence de metastase.")
    assert len(mask_negations(texte)) == len(texte)


def test_une_erreur_reste_locale():
    """C'est LA propriete qui distingue cette approche de la precedente : au
    pire un terme de trop est masque, jamais une phrase entiere."""
    phrase = (
        "Pas de dysplasie de haut grade de bas grade severe moderee legere, "
        "adenocarcinome lieberkuhnien infiltrant du colon sigmoide."
    )
    assert "adenocarcinome" in _reste(phrase)


def test_un_texte_sans_negation_est_intact():
    texte = normaliser("Adenocarcinome lieberkuhnien infiltrant du colon.")
    assert mask_negations(texte) == texte


def test_texte_vide():
    assert mask_negations("") == ""


def test_les_declencheurs_couvrent_les_trois_apostrophes():
    """Droite, typographique, et l'elision non transcrite de la dictee vocale."""
    assert "absence d'" in DECLENCHEURS
    assert "absence d’" in DECLENCHEURS
    assert "absence d " in DECLENCHEURS


def test_est_nie_ne_repond_que_sur_un_terme_present():
    assert not est_nie("Adenocarcinome du colon.", "melanome")
    assert est_nie("Absence d'adenocarcinome.", "adenocarcinome")
    assert not est_nie("Adenocarcinome infiltrant du colon.", "adenocarcinome")


def test_est_nie_est_faux_si_une_occurrence_echappe():
    """Un terme nie a un endroit et affirme a un autre n'est pas nie : c'est
    l'affirmation qui doit primer, sinon on manquerait la lesion."""
    texte = "Absence d'adenocarcinome sur la premiere biopsie. Adenocarcinome sur la seconde."
    assert not est_nie(texte, "adenocarcinome")
