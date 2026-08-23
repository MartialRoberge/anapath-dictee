"""Contenu des questionnaires de l'etude.

Les items vivent ici, pas dans le frontend : le depouillement doit pouvoir
associer une reponse a un libelle exact des mois plus tard, et un libelle
recopie a la main dans un composant React derive au premier remaniement.

Un mot sur le F-SUS. Sa formulation francaise est un instrument PUBLIE et
VALIDE (Gronier & Baudet, 2021). Le retraduire soi-meme detruit precisement ce
qui rend le score comparable a la litterature : un F-SUS paraphrase n'est plus
un F-SUS, et le score qu'il produit n'a aucune valeur publiable. Les dix items
sont donc declares avec leur polarite et leur cotation, mais leur LIBELLE reste
vide jusqu'a ce qu'il soit recopie mot pour mot depuis la source. La fonction
`fsus_pret()` dit si c'est fait ; tant que non, le questionnaire de fin
d'etude ne doit pas etre servi.

Reference : docs/specs/spec/MARC_cahier_de_recueil.md section 6.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Final

from etude.vocabulaire import (
    CADENCE_PERIODIQUE,
    QUESTIONNAIRE_FIN_ETUDE,
    QUESTIONNAIRE_INCLUSION,
    QUESTIONNAIRE_PAR_CAS,
    QUESTIONNAIRE_PERIODIQUE,
)

#: Ancres par famille d'echelle. Elles sont declarees ici, une fois, plutot
#: que repetees sur chaque item.
ACCORD: Final[tuple[str, str]] = ("Pas du tout d'accord", "Tout a fait d'accord")
DEGRE: Final[tuple[str, str]] = ("Pas du tout", "Tout a fait")
FREQUENCE: Final[tuple[str, str]] = ("Jamais", "Toujours")
INTENSITE: Final[tuple[str, str]] = ("Tres faible", "Tres elevee")
PROBABILITE: Final[tuple[str, str]] = ("Pas du tout probable", "Tout a fait probable")

# --- Types d'items ---------------------------------------------------------

LIKERT_5: Final = "likert_5"
ECHELLE_10: Final = "echelle_10"
CHOIX_UNIQUE: Final = "choix_unique"
CHOIX_MULTIPLE: Final = "choix_multiple"
TEXTE_LIBRE: Final = "texte_libre"
NOMBRE: Final = "nombre"
OUI_NON: Final = "oui_non"
CLASSEMENT: Final = "classement"


@dataclass(frozen=True)
class Item:
    """Un item de questionnaire.

    `depend_de` porte l'identifiant d'un item precedent : l'item ne s'affiche
    que si celui-la a recu une reponse autre que la premiere option. C'est ce
    qui evite de demander « lequel ? » a quelqu'un qui vient de repondre
    « jamais ».
    """

    id: str
    libelle: str
    type: str
    options: tuple[str, ...] = ()
    obligatoire: bool = False
    inverse: bool = False
    depend_de: str | None = None
    #: Ancres des echelles, cote SERVEUR et par item.
    #:
    #: Une constante cote frontend appliquerait les memes ancres a toutes les
    #: echelles a cinq points. Or elles ne mesurent pas la meme chose : les
    #: items par cas sont des AFFIRMATIONS, qu'on cote en accord ; le PDQI-9
    #: cote un DEGRE de qualite ; et un item formule en question n'appelle pas
    #: "tout a fait d'accord" comme reponse. Coter un instrument publie sur les
    #: mauvaises ancres, c'est la meme faute que le retraduire.
    ancre_basse: str = ""
    ancre_haute: str = ""


@dataclass(frozen=True)
class Questionnaire:
    """Un questionnaire complet, pret a etre servi au frontend."""

    nom: str
    titre: str
    duree_estimee_s: int
    items: tuple[Item, ...] = field(default_factory=tuple)


# --- Inclusion (une fois, ~5 minutes) --------------------------------------

_EXERCICE: Final = ("CHU", "CH", "Liberal", "Mixte")
_REDACTION: Final = (
    "Saisie clavier",
    "Dictee avec transcription humaine",
    "Reconnaissance vocale",
    "Mixte",
)
_USAGE_IA: Final = (
    "Jamais",
    "Une ou deux fois",
    "Occasionnellement",
    "Regulierement",
    "Systematiquement",
)

INCLUSION: Final = Questionnaire(
    nom=QUESTIONNAIRE_INCLUSION,
    titre="Avant de commencer",
    duree_estimee_s=300,
    items=(
        Item("inclusion_01", "Annees d'exercice en anatomopathologie", NOMBRE, obligatoire=True),
        Item("inclusion_02", "Type d'exercice", CHOIX_UNIQUE, _EXERCICE, obligatoire=True),
        Item("inclusion_03", "Nombre approximatif de comptes rendus par semaine", NOMBRE),
        Item("inclusion_04", "Localisations les plus frequentes dans votre activite", TEXTE_LIBRE),
        Item("inclusion_05", "Comment redigez-vous habituellement vos comptes rendus ?",
             CHOIX_UNIQUE, _REDACTION, obligatoire=True),
        Item("inclusion_06", "Si reconnaissance vocale, laquelle ?", TEXTE_LIBRE,
             depend_de="inclusion_05"),
        Item("inclusion_07",
             "Temps moyen consacre a la redaction d'un compte rendu de routine (minutes)",
             NOMBRE),
        Item("inclusion_08",
             "La redaction represente-t-elle une charge pesante dans votre activite ?", LIKERT_5, ancre_basse=DEGRE[0], ancre_haute=DEGRE[1]),
        # Item 9 : la question qui portera le resume de l'etude. Comparer a une
        # pratique reelle vaut mieux qu'affirmer une superiorite sans mesure.
        Item("inclusion_09",
             "Avez-vous deja utilise un assistant d'IA generative (ChatGPT, Claude, Copilot, "
             "autre) pour rediger, reformuler ou structurer un compte rendu ?",
             CHOIX_UNIQUE, _USAGE_IA, obligatoire=True),
        Item("inclusion_10", "Si oui : lequel ou lesquels ?", TEXTE_LIBRE,
             depend_de="inclusion_09"),
        Item("inclusion_11", "Si oui : pour quoi faire ?", CHOIX_MULTIPLE,
             ("Mise en forme", "Reformulation", "Traduction",
              "Redaction de la conclusion", "Recherche d'information", "Autre"),
             depend_de="inclusion_09"),
        Item("inclusion_12",
             "Si oui : saviez-vous ou sont hebergees les donnees transmises ?",
             CHOIX_UNIQUE, ("Oui", "Non", "Je ne me suis pas pose la question"),
             depend_de="inclusion_09"),
        Item("inclusion_13", "Cet usage vous pose-t-il un probleme de confidentialite ?",
             LIKERT_5, ancre_basse=DEGRE[0], ancre_haute=DEGRE[1], depend_de="inclusion_09"),
        Item("inclusion_14", "Faites-vous confiance a ce que produit un tel assistant ?",
             LIKERT_5, ancre_basse=DEGRE[0], ancre_haute=DEGRE[1], depend_de="inclusion_09"),
        Item("inclusion_15",
             "Qu'attendez-vous en priorite d'un outil d'assistance a la redaction ?",
             CLASSEMENT,
             ("Gagner du temps", "Reduire les oublis",
              "Homogeneiser mes comptes rendus", "Reduire la fatigue")),
    ),
)


# --- Apres chaque cas (~40 secondes) ---------------------------------------

#: Affiche immediatement apres la validation, jamais en fin de session : les
#: jugements retrospectifs globaux sont peu fiables.
PAR_CAS: Final = Questionnaire(
    nom=QUESTIONNAIRE_PAR_CAS,
    titre="Sur ce cas",
    duree_estimee_s=60,
    items=(
        # --- Ce que l'instrumentation ne peut PAS produire seule -----------
        #
        # Un oubli ne laisse aucune trace : le systeme ne sait pas ce qu'il n'a
        # pas ecrit.
        Item("par_cas_00", "Quelque chose que vous avez dicte a-t-il ete omis ?",
             OUI_NON, obligatoire=True),
        Item("par_cas_00b", "Lequel ?", TEXTE_LIBRE, depend_de="par_cas_00"),
        # L'ATTESTATION. Sans elle, on ne sait pas si le praticien SIGNERAIT ce
        # compte rendu — et un CR valide dans une etude mais qu'on ne signerait
        # pas en routine ne prouve rien de ce que l'etude pretend montrer.
        Item("par_cas_00c",
             "Je considere ce compte rendu comme termine, et je le validerais "
             "tel quel dans ma pratique courante.",
             OUI_NON, obligatoire=True),
        # Une erreur que le systeme a AFFIRMEE sans la soumettre echappe a toute
        # decision, donc a toute telemetrie. C'est le point aveugle, et cette
        # question est le seul instrument qui le regarde.
        Item("par_cas_01",
             "Avez-vous du corriger une erreur introduite par le logiciel ?",
             OUI_NON, obligatoire=True),
        Item("par_cas_01b", "Laquelle ?", TEXTE_LIBRE, depend_de="par_cas_01"),

        # --- Ce que le vecu seul peut dire ---------------------------------
        Item("par_cas_02", "Les suggestions de completude m'ont ete utiles sur ce cas.",
             LIKERT_5, ("Non applicable",),
             ancre_basse=ACCORD[0], ancre_haute=ACCORD[1]),
        # La mesure d'explicabilite declaree. Le cahier interdit son retrait
        # meme pour raccourcir : aucune telemetrie ne dit si le praticien a
        # COMPRIS, seulement s'il a ouvert un panneau.
        Item("par_cas_03", "J'ai compris pourquoi le systeme proposait ce qu'il proposait.",
             LIKERT_5, obligatoire=True,
             ancre_basse=ACCORD[0], ancre_haute=ACCORD[1]),
        Item("par_cas_04", "Le logiciel a facilite la redaction de ce compte rendu.",
             LIKERT_5, ancre_basse=ACCORD[0], ancre_haute=ACCORD[1]),
        # LA question que la telemetrie ne peut PAS repondre, contrairement a ce
        # qu'on croit d'abord.
        #
        # Une suggestion de completude acceptee dit que le praticien a ajoute le
        # champ. Elle ne dit PAS qu'il l'avait oublie : il pouvait etre sur le
        # point de l'ecrire et simplement content qu'on le lui rappelle. Les deux
        # se ressemblent dans la base et n'ont pas la meme valeur — seul le
        # premier cas est une affirmation de securite, le second n'est qu'un
        # confort. Le praticien est le seul a savoir lequel des deux s'est
        # produit, donc on le lui demande.
        Item("par_cas_04b",
             "Le logiciel vous a-t-il signale quelque chose que vous n'auriez "
             "pas ecrit sans lui ?",
             CHOIX_UNIQUE,
             ("Oui, je l'aurais omis",
              "Oui, mais je l'aurais ecrit de toute facon",
              "Non"),
             obligatoire=True),
        Item("par_cas_05", "Par rapport a ma pratique habituelle, ce compte rendu m'a pris :",
             CHOIX_UNIQUE,
             ("Beaucoup plus de temps", "Plus", "Autant", "Moins", "Beaucoup moins")),
        # L'item qui porte la conclusion de l'etude, et le seul qui la porte
        # sous une forme que le praticien reconnaitrait comme la sienne.
        Item("par_cas_06",
             "Globalement, auriez-vous prefere rediger ce compte rendu :",
             CHOIX_UNIQUE, ("Avec le logiciel", "Sans le logiciel", "Indifferent"),
             obligatoire=True),
        Item("par_cas_07", "Un mot si vous voulez (facultatif)", TEXTE_LIBRE),
    ),
)

#: Items ECARTES a dessein, parce que la donnee les repond deja mieux :
#:
#: - "la proposition correspondait a ce que j'ai dicte" -> chaque proposition
#:   est deja jugee une par une ; la question rendrait un jugement global, plus
#:   flou, sur ce que le detail mesure exactement.
#: - "j'ai du faire beaucoup de corrections" -> la distance d'edition entre le
#:   texte propose et le texte valide la mesure objectivement, sans dependre du
#:   souvenir qu'en garde le praticien.
#:
#: En revanche "le logiciel vous a-t-il signale quelque chose que vous n'auriez
#: pas ecrit" a ete REMIS apres coup : on avait cru la donnee suffisante, a
#: tort. Une suggestion acceptee dit que le champ a ete ajoute, jamais qu'il
#: avait ete oublie — et c'est pourtant toute la difference entre une
#: affirmation de securite et un confort de redaction.
#:
#: Chaque question retiree rend du temps a celles que rien ne remplace.

#: Ordre de retrait si le rodage montre que 40 secondes est deja trop (cahier
#: §6.2). par_cas_04 n'y figure pas : il ne se retire jamais.
ORDRE_DE_RETRAIT_PAR_CAS: Final[tuple[str, ...]] = ("par_cas_04", "par_cas_02")


# --- Fin d'etude (~15 minutes) ---------------------------------------------

#: Les dix items du F-SUS, sans libelle. Voir l'avertissement en tete de module :
#: la formulation doit etre recopiee mot pour mot depuis Gronier & Baudet (2021),
#: International Journal of Human-Computer Interaction, 37(16), 1571-1582.
#: Un F-SUS paraphrase n'est plus un F-SUS.
FSUS_ITEMS: Final[tuple[Item, ...]] = tuple(
    Item(
        id=f"fsus_{rang:02d}",
        libelle="",  # a recopier depuis la source publiee
        type=LIKERT_5,
        obligatoire=True,
        inverse=(rang % 2 == 0),  # polarite alternee : les items pairs sont negatifs
        # Ancres vides comme les libelles : elles font partie de l'instrument
        # publie et se recopient depuis la source, elles ne s'improvisent pas.
    )
    for rang in range(1, 11)
)

PDQI9_DIMENSIONS: Final[tuple[str, ...]] = (
    "A jour", "Exact", "Comprehensible", "Utile", "Organise",
    "Concis", "Coherent en interne", "Succinct", "Synthetique",
)

CHARGE_TRAVAIL: Final[tuple[Item, ...]] = tuple(
    Item(f"charge_{rang:02d}", libelle, ECHELLE_10,
         ancre_basse=INTENSITE[0], ancre_haute=INTENSITE[1])
    for rang, libelle in enumerate(
        ("Exigence mentale", "Rythme", "Effort", "Frustration"), start=1
    )
)

_COMPARATIF: Final = (
    "Nettement moins bon", "Moins bon", "Equivalent", "Meilleur", "Nettement meilleur",
)

COMPARAISON_PRATIQUE: Final[tuple[Item, ...]] = (
    Item("comparaison_01", "Le temps", CHOIX_UNIQUE, _COMPARATIF),
    Item("comparaison_02", "La qualite du compte rendu", CHOIX_UNIQUE, _COMPARATIF),
    Item("comparaison_03", "La charge mentale", CHOIX_UNIQUE, _COMPARATIF),
)

#: Servis uniquement a qui a declare un usage d'assistant generaliste (item 9
#: de l'inclusion). C'est la comparaison que l'etude peut honnetement porter :
#: un usage reel contre un usage reel, sans bras controle fabrique.
_AXES_ASSISTANT: Final = (
    "Justesse du contenu", "Possibilite de verifier", "Confiance", "Confort d'usage",
)

COMPARAISON_ASSISTANT: Final[tuple[Item, ...]] = tuple(
    Item(
        id=f"assistant_{rang:02d}",
        libelle=f"Par rapport a l'assistant que vous utilisiez — {axe}",
        type=CHOIX_UNIQUE,
        options=("Moins bon", "Equivalent", "Meilleur"),
        depend_de="inclusion_09",
    )
    for rang, axe in enumerate(_AXES_ASSISTANT, start=1)
)

INTENTION: Final[tuple[Item, ...]] = (
    Item("intention_01", "Souhaitez-vous continuer a utiliser l'outil ?",
         CHOIX_UNIQUE, ("Oui", "Non", "Peut-etre")),
    Item("intention_02", "Pourquoi ?", TEXTE_LIBRE),
    Item("intention_03", "Le recommanderiez-vous a un confrere ?", ECHELLE_10,
         ancre_basse=PROBABILITE[0], ancre_haute=PROBABILITE[1]),
    Item("intention_04", "Qu'est-ce qui vous a le plus gene ?", TEXTE_LIBRE),
    Item("intention_05",
         "Qu'est-ce qui vous manquerait le plus si on vous le retirait demain ?",
         TEXTE_LIBRE),
)


def periodique() -> Questionnaire:
    """Le F-SUS, tous les CADENCE_PERIODIQUE comptes rendus clos.

    Repete plutot qu'unique : un point ne distingue pas un outil qu'on apprend
    a aimer d'un outil dont on se lasse, une courbe si.
    """
    return Questionnaire(
        nom=QUESTIONNAIRE_PERIODIQUE,
        titre=f"Apres {CADENCE_PERIODIQUE} comptes rendus",
        duree_estimee_s=120,
        items=FSUS_ITEMS,
    )


def fin_etude() -> Questionnaire:
    """Assemble le questionnaire de fin d'etude."""
    # Le PDQI-9 cote un DEGRE de qualite documentaire, dimension par dimension.
    # Le coter en accord ("tout a fait d'accord" que le CR est "Exact") change
    # la question posee : c'est la meme faute que retraduire le F-SUS.
    pdqi = tuple(
        Item(f"pdqi_{rang:02d}", dimension, LIKERT_5,
             ancre_basse=DEGRE[0], ancre_haute=DEGRE[1])
        for rang, dimension in enumerate(PDQI9_DIMENSIONS, start=1)
    )
    return Questionnaire(
        nom=QUESTIONNAIRE_FIN_ETUDE,
        titre="Pour finir",
        duree_estimee_s=600,
        # Le F-SUS n'y figure plus : il est releve tous les
        # CADENCE_PERIODIQUE cas, et le dernier releve EST la mesure finale.
        # Le redemander ici ferait un doublon a quelques jours d'intervalle.
        items=(
            *pdqi, *CHARGE_TRAVAIL,
            *COMPARAISON_PRATIQUE, *COMPARAISON_ASSISTANT, *INTENTION,
        ),
    )


def fsus_pret() -> bool:
    """Les dix items du F-SUS ont-ils recu leur libelle publie ?

    Libelles ET ancres : un F-SUS cote sur des ancres improvisees n'est pas
    plus comparable qu'un F-SUS retraduit. Tant que les deux ne sont pas en
    place, le questionnaire de fin d'etude ne doit pas etre servi.
    """
    return all(
        item.libelle.strip() and item.ancre_basse.strip() and item.ancre_haute.strip()
        for item in FSUS_ITEMS
    )


def score_fsus(reponses: dict[str, int]) -> float | None:
    """Score F-SUS de 0 a 100, selon la cotation standard du SUS.

    Items impairs : reponse moins 1. Items pairs : 5 moins la reponse. Somme
    multipliee par 2,5. Un item manquant rend le score incalculable — mieux
    vaut None qu'un score partiel qu'on prendrait pour un score complet.
    """
    total = 0
    for rang in range(1, 11):
        reponse = reponses.get(f"fsus_{rang:02d}")
        if reponse is None or not 1 <= reponse <= 5:
            return None
        total += (reponse - 1) if rang % 2 else (5 - reponse)
    return round(total * 2.5, 1)


CATALOGUE: Final[dict[str, Questionnaire]] = {
    QUESTIONNAIRE_INCLUSION: INCLUSION,
    QUESTIONNAIRE_PAR_CAS: PAR_CAS,
    QUESTIONNAIRE_PERIODIQUE: periodique(),
    QUESTIONNAIRE_FIN_ETUDE: fin_etude(),
}
