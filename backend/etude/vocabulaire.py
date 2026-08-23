"""Valeurs autorisees de l'instrumentation.

Un seul endroit pour les vocabulaires fermes de l'etude. Toute valeur ecrite en
base doit venir d'ici : c'est ce qui garantit qu'un export se depouille sans
avoir a nettoyer des variantes d'orthographe.

Les libelles sont ceux de docs/specs/spec/MARC_cahier_de_recueil.md section 3.
"""

from __future__ import annotations

from typing import Final

# --- Types de proposition (cahier §7) -------------------------------------

TYPE_RESTITUTION: Final = "restitution"
TYPE_CODE: Final = "code"
TYPE_COMPLETUDE: Final = "completude"

TYPES_PROPOSITION: Final[frozenset[str]] = frozenset(
    {TYPE_RESTITUTION, TYPE_CODE, TYPE_COMPLETUDE}
)

# --- Decisions, par type de proposition (cahier §3) ------------------------
# Trois grilles distinctes : les confondre fausserait les taux publies.

#: §3.1 — propositions de restitution. "non_dicte" EST la mesure d'hallucination.
DECISIONS_RESTITUTION: Final[frozenset[str]] = frozenset({
    "conforme",     # je valide tel quel        -> acceptation sans modification
    "corrige",      # juste sur le fond         -> charge d'edition
    "non_dicte",    # je n'ai pas dit ca        -> HALLUCINATION
    "hors_sujet",   # non pertinent ici         -> bruit
})

#: §3.2 — codes ADICAP. "je_ne_sais_pas" n'entre ni au numerateur ni au
#: denominateur de l'exactitude : sans lui on mesure de l'acquiescement.
DECISIONS_CODE: Final[frozenset[str]] = frozenset({
    "juste",
    "corrige",
    "je_ne_sais_pas",
})

#: §3.3 — suggestions de completude. "pertinent_non_retenu" n'est PAS un faux
#: positif : un praticien qui juge la suggestion pertinente et choisit
#: souverainement de ne pas l'ecrire valide le systeme.
DECISIONS_COMPLETUDE: Final[frozenset[str]] = frozenset({
    "pertinent_ajoute",
    "pertinent_non_retenu",
    "non_pertinent",
})

DECISIONS_PAR_TYPE: Final[dict[str, frozenset[str]]] = {
    TYPE_RESTITUTION: DECISIONS_RESTITUTION,
    TYPE_CODE: DECISIONS_CODE,
    TYPE_COMPLETUDE: DECISIONS_COMPLETUDE,
}


def decision_valide(type_proposition: str, decision: str) -> bool:
    """La decision appartient-elle a la grille de ce type de proposition ?"""
    return decision in DECISIONS_PAR_TYPE.get(type_proposition, frozenset())


# --- Nature d'une correction ----------------------------------------------
#
# LA question que "corrige" seul ne repond pas : le praticien a-t-il corrige
# parce que le systeme s'est TROMPE, ou parce qu'il ecrit AUTREMENT ?
#
# Sans cette distinction, toute correction compte comme un echec du systeme, et
# le taux publie melange deux choses qui n'ont rien a voir : une reformulation
# de confort et une erreur de fond. Un outil dont 40 % des propositions sont
# reecrites en style maison n'est pas un outil a 40 % d'erreurs — mais un
# tableau qui ne separe pas les deux le dira.
#
# Consequence pour l'analyse : "conforme" + "corrige en style" = le systeme
# avait raison sur le fond. C'est ce total-la qui mesure la justesse.

NATURES_CORRECTION: Final[frozenset[str]] = frozenset({
    # Le fond etait juste ; le praticien reformule a sa main ou a celle du
    # laboratoire. Le systeme a REUSSI ; c'est la couche "style de la maison"
    # qui a du travail, pas la couche de restitution.
    "style",
    # Le fond etait juste mais incomplet : le praticien ajoute une precision
    # que le systeme n'avait pas de quoi produire. Succes partiel.
    "precision",
    # Le fond etait FAUX. C'est le seul cas qui compte comme une erreur du
    # systeme, et c'est le seul qui appelle une cause.
    "erreur_fond",
})

#: Natures qui n'imputent PAS d'erreur au systeme. Sert de denominateur au
#: taux de justesse sur le fond.
NATURES_SANS_ERREUR: Final[frozenset[str]] = frozenset({"style", "precision"})


def impute_une_erreur(nature: str | None) -> bool:
    """Cette correction compte-t-elle comme une erreur du systeme ?

    Une nature non renseignee ne s'impute pas : on ne fabrique pas une erreur
    a partir d'une absence de reponse.
    """
    return nature == "erreur_fond"


# --- Cause d'erreur (cahier §3.1, question facultative sur ✎ et ✗) ---------
# Separe les deux mecanismes d'erreur maintenant qu'il n'y a plus d'audio.
# Ne se pose que sur une erreur de FOND : demander la cause d'une reformulation
# de style n'a pas de sens et ferait perdre un geste.

CAUSES_ERREUR: Final[frozenset[str]] = frozenset({
    "transcription",    # la transcription a mal compris un mot
    "interpretation",   # la transcription etait juste, l'interpretation est fausse
})

# --- Motifs d'abandon (cahier §4, garde-fou n°1) ---------------------------
# Sans porte de sortie, on obtient des validations de complaisance et l'etude
# est fausse tout en paraissant parfaite.

MOTIFS_ABANDON: Final[frozenset[str]] = frozenset({
    "outil_trop_lent",
    "propositions_inexploitables",
    "interruption",
    "cas_trop_complexe",
    "autre",
})

# --- Sources de doute d'une question (Politique_de_questions §4) -----------

SOURCES_DOUTE: Final[frozenset[str]] = frozenset({
    "structurelle",     # ambiguite connue du referentiel, question pre-redigee
    "transcription",    # divergence n-best sur un empan porteur de decision
    "regle",            # conflit detecte par le moteur deterministe
})

# --- Causes de pause (cahier §5) ------------------------------------------

CAUSES_PAUSE: Final[frozenset[str]] = frozenset({
    "onglet_masque",    # Page Visibility API
    "inactivite",       # plus de 90 s sans evenement
})

#: Seuil d'inactivite au-dela duquel l'horloge se met en pause, retroactivement
#: a partir de la derniere action (cahier §5).
SEUIL_INACTIVITE_S: Final[int] = 90

#: Une decision plus rapide que ce seuil, sur une proposition plus longue que
#: SEUIL_HATIVE_MOTS, est marquee `hative` et analysee a part (cahier §4).
SEUIL_HATIVE_MS: Final[int] = 1200
SEUIL_HATIVE_MOTS: Final[int] = 15


def est_hative(latence_ms: int | None, longueur_mots: int | None) -> bool:
    """Decision trop rapide pour avoir ete lue ? (cahier §4, garde-fou n°2)

    Le verrou d'export cree une pression a cliquer vite : sans ce marqueur, il
    fabrique un taux de completion de 100 % qui ne veut rien dire.
    """
    if latence_ms is None or longueur_mots is None:
        return False
    return latence_ms < SEUIL_HATIVE_MS and longueur_mots > SEUIL_HATIVE_MOTS


# --- Questionnaires (cahier §6) -------------------------------------------

QUESTIONNAIRE_INCLUSION: Final = "inclusion"
QUESTIONNAIRE_PAR_CAS: Final = "par_cas"
QUESTIONNAIRE_PERIODIQUE: Final = "periodique"
QUESTIONNAIRE_FIN_ETUDE: Final = "fin_etude"

QUESTIONNAIRES: Final[frozenset[str]] = frozenset({
    QUESTIONNAIRE_INCLUSION,
    QUESTIONNAIRE_PAR_CAS,
    QUESTIONNAIRE_PERIODIQUE,
    QUESTIONNAIRE_FIN_ETUDE,
})

#: Le F-SUS revient tous les N comptes rendus clos, au lieu d'une seule fois.
#:
#: Deux raisons. Il mesure l'utilisabilite d'un SYSTEME apres usage, pas une
#: tache : le poser apres chaque cas produirait 250 reponses qui ne se somment
#: pas en un score valide, et ferait decrocher le praticien. Mais le poser une
#: seule fois, a la fin, ne donne qu'un point — alors que repete, il donne une
#: COURBE, et une courbe distingue un outil qu'on apprend a aimer d'un outil
#: dont on se lasse. C'est une mesure repetee, et cela se publie.
CADENCE_PERIODIQUE: Final[int] = 5


def periodique_du(nb_dossiers_clos: int) -> bool:
    """Le questionnaire periodique est-il du apres ce dossier ?

    Compte cote SERVEUR : un decompte tenu par le client deriverait d'un poste
    a l'autre, et la courbe ne serait plus alignee entre praticiens.
    """
    return nb_dossiers_clos > 0 and nb_dossiers_clos % CADENCE_PERIODIQUE == 0
