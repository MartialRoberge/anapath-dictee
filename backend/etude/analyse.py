"""Calcul des indicateurs de l'etude.

Ce module ne fait pas de statistique : il compte. Mais il compte au bon endroit,
et c'est tout l'enjeu — un denominateur mal choisi produit un taux flatteur qui
ne resiste pas a une relecture par les pairs.

Trois regles, appliquees partout ici :

1. UN TAUX SANS SON DENOMINATEUR N'EST PAS UN RESULTAT. Chaque indicateur
   expose son numerateur et son denominateur bruts. Un lecteur doit pouvoir
   refaire le calcul.
2. "JE NE SAIS PAS" N'EST PAS UNE ERREUR, ET PAS UNE REUSSITE. Sur les codes,
   cette reponse sort des DEUX termes du rapport. La compter comme un echec
   punirait l'honnetete ; la compter comme une reussite mesurerait de
   l'acquiescement.
3. LES DECISIONS HATIVES SONT ISOLEES, PAS SUPPRIMEES. Le verrou d'export cree
   une pression a cliquer vite. Chaque taux est donc calcule deux fois — toutes
   decisions, puis hors decisions hatives — et l'ecart entre les deux est
   lui-meme un resultat sur la validite du protocole.
4. CE QUE LA TELEMETRIE NE PEUT PAS PRODUIRE SE DEMANDE. Un oubli ne laisse
   aucune trace ; un panneau ouvert ne dit pas que le praticien a COMPRIS ; une
   erreur affirmee sans etre soumise n'est jamais decidee. Les items declares
   sont donc depouilles ici au meme titre que les decisions, et non relegues a
   un commentaire de discussion.
5. UN INDICATEUR SANS EFFECTIF NE SE PUBLIE PAS. Un F-SUS moyen sur deux
   releves n'a pas le poids d'un F-SUS moyen sur quarante. Chaque agregat porte
   donc son effectif, et le tableau de couverture dit, critere par critere, si
   l'on a de quoi conclure.

Reference : docs/specs/etude/Protocole_etude_MARC.md.
"""

from __future__ import annotations

import statistics
from collections import Counter
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Final

from etude.questionnaires import CATALOGUE, fsus_comparable, score_fsus
from etude.vocabulaire import (
    QUESTIONNAIRE_FIN_ETUDE,
    QUESTIONNAIRE_PAR_CAS,
    QUESTIONNAIRE_PERIODIQUE,
    TYPE_CODE,
    TYPE_COMPLETUDE,
    TYPE_RESTITUTION,
)


@dataclass(frozen=True)
class Taux:
    """Un rapport, toujours accompagne de ses deux termes bruts.

    `valeur` vaut None quand le denominateur est nul : c'est une absence de
    mesure, pas un zero. Ecrire 0 % la ou l'on n'a rien observe est la maniere
    la plus courante de mentir avec un tableau.
    """

    numerateur: int
    denominateur: int
    libelle: str = ""

    @property
    def valeur(self) -> float | None:
        if self.denominateur == 0:
            return None
        return round(self.numerateur / self.denominateur, 4)

    def en_dict(self) -> dict[str, object]:
        return {
            "libelle": self.libelle,
            "numerateur": self.numerateur,
            "denominateur": self.denominateur,
            "valeur": self.valeur,
        }


@dataclass
class DecisionObservee:
    """Une decision, reduite a ce dont le calcul a besoin.

    Une structure de lecture plutot que l'ORM : les indicateurs se testent alors
    sans base, et le depouillement ne depend pas du schema du jour.
    """

    type_proposition: str
    decision: str | None
    hative: bool = False
    latence_ms: int | None = None
    decision_changee_apres_justif: bool = False
    #: Pourquoi le praticien a corrige : le systeme s'est-il TROMPE, ou ecrit-il
    #: AUTREMENT ? Sans elle, une reformulation de confort et une erreur
    #: clinique comptent pareil.
    nature_correction: str | None = None
    #: Un empan de la dictee soutient-il l'assertion ? Faux = le systeme a
    #: affirme quelque chose que rien dans le verbatim ne porte.
    ancree: bool = True


@dataclass(frozen=True)
class AgregatCorrections:
    """La nature des corrections : erreur du systeme, ou main du praticien ?

    C'est la distinction que "corrige" seul ne porte pas. Un outil dont 40 % des
    propositions sont reecrites en style maison n'est pas un outil a 40 %
    d'erreurs — mais un tableau qui ne separe pas les deux le dira, et personne
    ne pourra le contredire.

    `justesse_sur_le_fond` est le chiffre a publier en regard : accepte tel quel
    ou reecrit pour la seule forme, rapporte a toutes les restitutions decidees.
    """

    corrigees: int = 0
    style: Taux = field(default_factory=lambda: Taux(0, 0, "Corrigee en style"))
    precision: Taux = field(
        default_factory=lambda: Taux(0, 0, "Corrigee en precision")
    )
    erreur_fond: Taux = field(default_factory=lambda: Taux(0, 0, "Erreur de fond"))
    non_declaree: Taux = field(
        default_factory=lambda: Taux(0, 0, "Nature non declaree")
    )
    justesse_sur_le_fond: Taux = field(
        default_factory=lambda: Taux(0, 0, "Juste sur le fond")
    )

    def en_dict(self) -> dict[str, object]:
        return {
            "corrigees": self.corrigees,
            "taux": {
                nom: getattr(self, nom).en_dict()
                for nom in (
                    "style",
                    "precision",
                    "erreur_fond",
                    "non_declaree",
                    "justesse_sur_le_fond",
                )
            },
        }


@dataclass
class IndicateursPropositions:
    """Les taux calcules sur un ensemble de decisions."""

    decidees: int = 0
    non_decidees: int = 0
    acceptation_sans_modification: Taux = field(
        default_factory=lambda: Taux(0, 0, "Accepte sans modification")
    )
    hallucination: Taux = field(
        default_factory=lambda: Taux(0, 0, "Non dicte (hallucination)")
    )
    bruit: Taux = field(default_factory=lambda: Taux(0, 0, "Hors sujet (bruit)"))
    exactitude_codes: Taux = field(
        default_factory=lambda: Taux(0, 0, "Codes justes")
    )
    abstention_codes: Taux = field(
        default_factory=lambda: Taux(0, 0, "Codes : je ne sais pas")
    )
    utilite_completude: Taux = field(
        default_factory=lambda: Taux(0, 0, "Suggestions jugees pertinentes")
    )
    decisions_hatives: Taux = field(
        default_factory=lambda: Taux(0, 0, "Decisions hatives")
    )
    changement_apres_justification: Taux = field(
        default_factory=lambda: Taux(0, 0, "Avis change apres justification")
    )
    #: Le critere BLOQUANT du protocole : une assertion que rien dans la dictee
    #: ne soutient, et que le praticien a pourtant validee telle quelle.
    acceptation_non_ancree: Taux = field(
        default_factory=lambda: Taux(0, 0, "Non ancrees acceptees telles quelles")
    )
    corrections: AgregatCorrections = field(default_factory=AgregatCorrections)

    def en_dict(self) -> dict[str, object]:
        return {
            "decidees": self.decidees,
            "non_decidees": self.non_decidees,
            "taux": {
                nom: getattr(self, nom).en_dict()
                for nom in (
                    "acceptation_sans_modification",
                    "hallucination",
                    "bruit",
                    "exactitude_codes",
                    "abstention_codes",
                    "utilite_completude",
                    "decisions_hatives",
                    "changement_apres_justification",
                    "acceptation_non_ancree",
                )
            },
            "corrections": self.corrections.en_dict(),
        }


def calculer_indicateurs(
    decisions: list[DecisionObservee],
) -> IndicateursPropositions:
    """Compte les decisions et en tire les taux de l'etude."""
    prises = [d for d in decisions if d.decision is not None]
    restitutions = Counter(
        d.decision for d in prises if d.type_proposition == TYPE_RESTITUTION
    )
    codes = Counter(d.decision for d in prises if d.type_proposition == TYPE_CODE)
    completudes = Counter(
        d.decision for d in prises if d.type_proposition == TYPE_COMPLETUDE
    )

    total_restitution = sum(restitutions.values())
    # "je ne sais pas" sort des DEUX termes : le compter comme un echec
    # punirait l'honnetete, le compter comme une reussite mesurerait de
    # l'acquiescement.
    codes_tranches = codes["juste"] + codes["corrige"]
    # Une restitution sans empan verifie est une assertion que rien dans la
    # dictee ne soutient. L'accepter telle quelle est le point aveugle du
    # protocole, et son denominateur n'est pas le corpus entier mais ces
    # seules assertions-la.
    non_ancrees = [
        d for d in prises if d.type_proposition == TYPE_RESTITUTION and not d.ancree
    ]

    return IndicateursPropositions(
        decidees=len(prises),
        non_decidees=len(decisions) - len(prises),
        acceptation_sans_modification=Taux(
            restitutions["conforme"], total_restitution, "Accepte sans modification"
        ),
        hallucination=Taux(
            restitutions["non_dicte"], total_restitution, "Non dicte (hallucination)"
        ),
        bruit=Taux(restitutions["hors_sujet"], total_restitution, "Hors sujet (bruit)"),
        exactitude_codes=Taux(codes["juste"], codes_tranches, "Codes justes"),
        abstention_codes=Taux(
            codes["je_ne_sais_pas"], sum(codes.values()), "Codes : je ne sais pas"
        ),
        utilite_completude=Taux(
            completudes["pertinent_ajoute"] + completudes["pertinent_non_retenu"],
            sum(completudes.values()),
            "Suggestions jugees pertinentes",
        ),
        decisions_hatives=Taux(
            sum(1 for d in prises if d.hative), len(prises), "Decisions hatives"
        ),
        changement_apres_justification=Taux(
            sum(1 for d in prises if d.decision_changee_apres_justif),
            len(prises),
            "Avis change apres justification",
        ),
        acceptation_non_ancree=Taux(
            sum(1 for d in non_ancrees if d.decision == "conforme"),
            len(non_ancrees),
            "Non ancrees acceptees telles quelles",
        ),
        corrections=_corrections(
            prises, restitutions["conforme"], total_restitution
        ),
    )


def _corrections(
    prises: list[DecisionObservee], conformes: int, total_restitution: int
) -> AgregatCorrections:
    """Repartit les corrections par nature et en tire la justesse sur le fond.

    Le denominateur des natures est le nombre de propositions CORRIGEES, pas le
    total decide : rapporter une nature a l'ensemble des decisions la diluerait
    jusqu'a la rendre illisible.

    Une correction dont la nature n'a pas ete declaree n'est imputee a personne,
    et elle est comptee a part. Sans ce compte, trois natures qui ne somment pas
    a cent pour cent passeraient pour une erreur d'arrondi.
    """
    # RESTITUTIONS seulement, des deux cotes du bloc. Un code ADICAP corrige
    # n'a pas de "nature" au sens clinique — il est juste ou faux — et le
    # melanger aux restitutions donnait deux chiffres qui ne decrivaient pas la
    # meme population : le lecteur ne pouvait plus refaire le calcul.
    corrigees = [
        d
        for d in prises
        if d.decision == "corrige" and d.type_proposition == TYPE_RESTITUTION
    ]
    natures = Counter(d.nature_correction for d in corrigees)

    # "Le systeme avait raison sur le fond" = valide tel quel, ou reecrit pour
    # la seule forme. Une correction de PRECISION n'y entre pas : le fond etait
    # juste mais INCOMPLET, et compter un succes partiel comme une justesse
    # gonflerait le seul chiffre qui doive rester dur. Une correction dont la
    # nature n'a pas ete declaree n'y entre pas non plus : on ne fabrique pas
    # une reussite a partir d'une absence de reponse.
    en_style = sum(
        1
        for d in corrigees
        if d.type_proposition == TYPE_RESTITUTION and d.nature_correction == "style"
    )

    return AgregatCorrections(
        corrigees=len(corrigees),
        style=Taux(natures["style"], len(corrigees), "Corrigee en style"),
        precision=Taux(natures["precision"], len(corrigees), "Corrigee en precision"),
        erreur_fond=Taux(natures["erreur_fond"], len(corrigees), "Erreur de fond"),
        non_declaree=Taux(natures[None], len(corrigees), "Nature non declaree"),
        justesse_sur_le_fond=Taux(
            conformes + en_style, total_restitution, "Juste sur le fond"
        ),
    )


@dataclass
class Depouillement:
    """Les indicateurs, calcules deux fois.

    L'ecart entre `toutes` et `hors_hatives` mesure combien le verrou d'export
    a gonfle les resultats. Un ecart important invalide la lecture naive des
    taux et doit etre publie, pas gomme.
    """

    toutes: IndicateursPropositions
    hors_hatives: IndicateursPropositions

    def en_dict(self) -> dict[str, object]:
        return {
            "toutes_decisions": self.toutes.en_dict(),
            "hors_decisions_hatives": self.hors_hatives.en_dict(),
        }


def depouiller(decisions: list[DecisionObservee]) -> Depouillement:
    """Calcule les indicateurs avec puis sans les decisions hatives."""
    return Depouillement(
        toutes=calculer_indicateurs(decisions),
        hors_hatives=calculer_indicateurs([d for d in decisions if not d.hative]),
    )


# --- Temps ------------------------------------------------------------------


@dataclass
class TempsDossier:
    """Les durees d'un dossier, pauses deduites.

    Le referentiel de temps est celui de la REDACTION AVEC L'OUTIL (t2 -> t5),
    decision actee avec le proprietaire : c'est ce que le praticien vit, et
    c'est la seule duree comparable d'un cas a l'autre.
    """

    dictee_ms: int | None
    generation_ms: int | None
    revision_ms: int | None
    pauses_ms: int
    nb_pauses: int

    @property
    def revision_nette_ms(self) -> int | None:
        """Duree de revision hors interruptions."""
        if self.revision_ms is None:
            return None
        return max(0, self.revision_ms - self.pauses_ms)

    def en_dict(self) -> dict[str, object]:
        return {
            "dictee_ms": self.dictee_ms,
            "generation_ms": self.generation_ms,
            "revision_ms": self.revision_ms,
            "revision_nette_ms": self.revision_nette_ms,
            "pauses_ms": self.pauses_ms,
            "nb_pauses": self.nb_pauses,
        }


def _ecart_ms(depart, arrivee) -> int | None:
    """Millisecondes entre deux horodatages, ou None si l'un manque."""
    if depart is None or arrivee is None:
        return None
    return max(0, int((arrivee - depart).total_seconds() * 1000))


def calculer_temps(dossier, pauses_ms: int, nb_pauses: int) -> TempsDossier:
    """Extrait les durees d'un dossier a partir de ses horodatages."""
    return TempsDossier(
        dictee_ms=_ecart_ms(dossier.t0_debut_dictee, dossier.t1_fin_dictee),
        generation_ms=_ecart_ms(dossier.t1_fin_dictee, dossier.t2_affichage),
        revision_ms=_ecart_ms(dossier.t2_affichage, dossier.t5_cloture),
        pauses_ms=pauses_ms,
        nb_pauses=nb_pauses,
    )


# --- Effet d'apprentissage --------------------------------------------------


def terciles(valeurs: list[float]) -> list[list[float]]:
    """Decoupe une serie ordonnee en trois groupes de taille comparable.

    L'analyse par tercile sert a voir si le temps de revision baisse a mesure
    que le praticien s'habitue : sans ce decoupage, l'effet d'apprentissage se
    confondrait avec une performance de l'outil.
    """
    if not valeurs:
        return [[], [], []]
    taille = len(valeurs)
    premier = taille // 3
    second = 2 * taille // 3
    return [valeurs[:premier], valeurs[premier:second], valeurs[second:]]


def moyenne(valeurs: list[float]) -> float | None:
    """Moyenne, ou None sur une serie vide — jamais zero."""
    if not valeurs:
        return None
    return round(sum(valeurs) / len(valeurs), 2)


def mediane(valeurs: list[float]) -> float | None:
    """Mediane, ou None sur une serie vide — jamais zero.

    Mediane et pas moyenne partout ou l'on resume une DUREE : une seule
    interruption longue deplace une moyenne de plusieurs minutes et ferait
    conclure a une lenteur que personne n'a vecue.
    """
    if not valeurs:
        return None
    return round(statistics.median(valeurs), 2)


def ecart_type(valeurs: list[float]) -> float | None:
    """Ecart-type d'echantillon, ou None sous deux valeurs.

    Sur une mesure unique l'ecart-type n'existe pas ; en publier zero laisserait
    croire a une unanimite qu'on n'a pas observee.
    """
    if len(valeurs) < 2:
        return None
    return round(statistics.stdev(valeurs), 2)


@dataclass(frozen=True)
class Distribution:
    """Une serie resumee par sa mediane et son intervalle, avec son effectif.

    L'intervalle est publie avec la mediane parce qu'une mediane seule ne dit
    pas sur quoi elle porte : dix minutes mediane entre neuf et onze et dix
    minutes mediane entre deux et quarante ne decrivent pas le meme outil.
    """

    effectif: int
    mediane: float | None
    minimum: float | None
    maximum: float | None
    libelle: str = ""

    def en_dict(self) -> dict[str, object]:
        return {
            "libelle": self.libelle,
            "effectif": self.effectif,
            "mediane": self.mediane,
            "minimum": self.minimum,
            "maximum": self.maximum,
        }


def resumer(valeurs: list[float], libelle: str = "") -> Distribution:
    """Resume une serie. Une serie vide donne None partout, jamais zero."""
    return Distribution(
        effectif=len(valeurs),
        mediane=mediane(valeurs),
        minimum=round(min(valeurs), 2) if valeurs else None,
        maximum=round(max(valeurs), 2) if valeurs else None,
        libelle=libelle,
    )


@dataclass(frozen=True)
class Score:
    """Une moyenne, son ecart-type et son effectif.

    `non_cotables` compte les reponses recues mais impossibles a coter : item
    manquant, valeur hors echelle, option de sortie ("Non applicable"). Elles
    sortent de la moyenne mais restent VISIBLES — un F-SUS moyen sur trois
    releves cotables quand douze ont ete remplis dit surtout que le
    questionnaire ne se remplit pas en entier, et c'est cela qu'il faut lire.
    """

    effectif: int
    moyenne: float | None
    ecart_type: float | None
    non_cotables: int = 0
    libelle: str = ""

    def en_dict(self) -> dict[str, object]:
        return {
            "libelle": self.libelle,
            "effectif": self.effectif,
            "moyenne": self.moyenne,
            "ecart_type": self.ecart_type,
            "non_cotables": self.non_cotables,
        }


def coter(valeurs: list[float], non_cotables: int = 0, libelle: str = "") -> Score:
    """Resume une serie de cotations. Une serie vide donne None, jamais zero."""
    return Score(
        effectif=len(valeurs),
        moyenne=moyenne(valeurs),
        ecart_type=ecart_type(valeurs),
        non_cotables=non_cotables,
        libelle=libelle,
    )


# --- Reponses de questionnaire ----------------------------------------------
#
# La donnee brute dort dans etude_reponses_questionnaire depuis le premier cas.
# Ce qui suit la depouille : sans elle, la moitie des criteres de jugement du
# protocole n'a aucune valeur publiee, et l'etude ne couvre que ce que la
# telemetrie sait voir.


#: Items depouilles ici. Les LIBELLES ne sont pas recopies : ils vivent dans
#: etude.questionnaires, seule source, et un libelle duplique derive au premier
#: remaniement.
ITEM_OMISSION: Final = "par_cas_00"
ITEM_ATTESTATION: Final = "par_cas_00c"
ITEM_ERREUR_INTRODUITE: Final = "par_cas_01"
ITEM_COMPREHENSION: Final = "par_cas_03"
ITEM_OUBLI_RATTRAPE: Final = "par_cas_04b"
ITEM_PREFERENCE: Final = "par_cas_06"
ITEM_SOUHAIT_DE_CONTINUER: Final = "intention_01"

#: Un item oui/non ne porte pas d'options cote serveur : c'est le frontend qui
#: fixe la paire. Le depouillement compare donc sur la forme normalisee, pour
#: qu'un "OUI" ou un " oui " ne sorte pas silencieusement du denominateur.
_OUI: Final = "oui"
_NON: Final = "non"

#: Horodatage de repli d'une reponse qui n'en porte pas. Il trie en tete plutot
#: que de faire echouer le tri : une reponse sans date reste une reponse.
_JAMAIS: Final[datetime] = datetime.min.replace(tzinfo=UTC)


@dataclass
class ReponseObservee:
    """Une reponse de questionnaire, reduite a ce dont le calcul a besoin.

    Structure de lecture plutot que l'ORM, comme DecisionObservee : les
    indicateurs se testent alors sans base, et le depouillement ne depend pas du
    schema du jour.
    """

    praticien_id: str
    questionnaire: str
    item: str
    valeur: str
    dossier_id: str | None = None
    repondu_a: datetime | None = None


def retenir_reponses(
    reponses: list[ReponseObservee], dossiers_retenus: set[str]
) -> list[ReponseObservee]:
    """Ecarte les reponses attachees a un dossier exclu.

    Une exclusion qui n'exclut pas le questionnaire du meme cas laisserait un
    essai d'administrateur peser sur le taux d'omission — c'est-a-dire sur un
    critere de SECURITE.

    Une reponse SANS dossier (inclusion, releve periodique, fin d'etude) porte
    sur le praticien et non sur un cas : elle est conservee. Ecarter un cas
    d'essai ne doit pas effacer le F-SUS de celui qui l'a ouvert.
    """
    return [
        reponse
        for reponse in reponses
        if reponse.dossier_id is None or reponse.dossier_id in dossiers_retenus
    ]


def _horodatage(reponse: ReponseObservee) -> datetime:
    """Horodatage comparable d'une reponse.

    PostgreSQL restitue un datetime avec fuseau, SQLite un datetime nu :
    comparer les deux leve une TypeError, et le tri des releves casserait en
    developpement, la ou tourne justement le rodage avec les praticiens.
    """
    if reponse.repondu_a is None:
        return _JAMAIS
    if reponse.repondu_a.tzinfo is None:
        return reponse.repondu_a.replace(tzinfo=UTC)
    return reponse.repondu_a


def _entier(valeur: str) -> int | None:
    """Cotation lue en entier, ou None quand ce n'en est pas une."""
    try:
        return int(valeur.strip())
    except ValueError:
        return None


def _normaliser(valeur: str) -> str:
    """Forme comparable d'une reponse : casse et espaces ne sont pas du sens."""
    return valeur.strip().lower()


def _reponses_a(
    reponses: list[ReponseObservee], questionnaire: str, item: str
) -> list[ReponseObservee]:
    """Les reponses a un item precis d'un questionnaire precis."""
    return [
        reponse
        for reponse in reponses
        if reponse.questionnaire == questionnaire and reponse.item == item
    ]


def _options_declarees(questionnaire: str, item: str) -> tuple[str, ...]:
    """Les options d'un item, telles que le catalogue les declare."""
    modele = CATALOGUE.get(questionnaire)
    if modele is None:
        return ()
    for declare in modele.items:
        if declare.id == item:
            return declare.options
    return ()


def _option(questionnaire: str, item: str, rang: int) -> str:
    """L'option declaree d'un item, designee par son RANG.

    Recopier "Oui, je l'aurais omis" ici en ferait une seconde source de verite,
    qui divergerait au premier remaniement du questionnaire — et l'option
    disparaitrait du taux sans que rien ne le signale. L'ordre, lui, fait partie
    de l'instrument : la regle `depend_de` s'appuie deja dessus.
    """
    options = _options_declarees(questionnaire, item)
    return options[rang] if 0 <= rang < len(options) else ""


# --- Le score F-SUS ---------------------------------------------------------


#: Seuil du protocole (section 6) : un F-SUS moyen de 70 est la limite basse
#: publiable, 68 etant la moyenne etablie de la litterature SUS.
SEUIL_FSUS: Final[float] = 70.0


@dataclass(frozen=True)
class ReleveFsus:
    """Un passage du F-SUS pour un praticien, a son rang dans la serie."""

    praticien_id: str
    rang: int
    score: float | None


def decouper_releves_fsus(reponses: list[ReponseObservee]) -> list[ReleveFsus]:
    """Reconstitue les passages successifs du F-SUS, praticien par praticien.

    Le F-SUS revient tous les CADENCE_PERIODIQUE comptes rendus : les reponses
    d'un praticien portent donc DIX items repetes autant de fois qu'il y a eu de
    releves. Le decoupage se fait item par item (voir `_passages`).

    La cotation n'est pas refaite ici : c'est `etude.questionnaires.score_fsus`
    qui l'applique, avec la polarite alternee de l'instrument publie.
    """
    releves: list[ReleveFsus] = []
    for praticien, siennes in _par_praticien(_reponses_fsus(reponses)).items():
        for rang, passage in enumerate(_passages(siennes), start=1):
            releves.append(
                ReleveFsus(
                    praticien_id=praticien, rang=rang, score=_coter_passage(passage)
                )
            )
    return releves


def _reponses_fsus(reponses: list[ReponseObservee]) -> list[ReponseObservee]:
    """Les seules reponses qui cotent un F-SUS."""
    return [
        reponse
        for reponse in reponses
        if reponse.questionnaire == QUESTIONNAIRE_PERIODIQUE
        and reponse.item.startswith("fsus_")
    ]


def _par_praticien(
    reponses: list[ReponseObservee],
) -> dict[str, list[ReponseObservee]]:
    """Groupe des reponses par praticien."""
    groupes: dict[str, list[ReponseObservee]] = {}
    for reponse in reponses:
        groupes.setdefault(reponse.praticien_id, []).append(reponse)
    return groupes


def _passages(reponses: list[ReponseObservee]) -> list[dict[str, str]]:
    """Decoupe les reponses d'un praticien en passages successifs.

    LA REGLE : la k-ieme reponse a un item appartient au k-ieme passage.

    Ni l'horodatage seul ni l'ordre d'arrivee seul ne tiennent. Une base qui
    n'horodate qu'a la seconde peut dater deux releves de la MEME seconde, et
    peut aussi couper un SEUL releve sur deux secondes quand l'horloge tourne au
    milieu de l'insertion. Compter les occurrences item par item survit aux deux
    cas ; un decoupage sur l'horodatage transformait, lui, deux F-SUS complets
    en une dizaine de fragments incotables — c'est-a-dire qu'il detruisait en
    silence un critere PRINCIPAL du protocole.
    """
    passages: list[dict[str, str]] = []
    occurrences: Counter[str] = Counter()
    for reponse in sorted(reponses, key=lambda r: (r.item, _horodatage(r))):
        rang = occurrences[reponse.item]
        occurrences[reponse.item] += 1
        if rang == len(passages):
            passages.append({})
        passages[rang][reponse.item] = reponse.valeur
    return passages


def _coter_passage(passage: dict[str, str]) -> float | None:
    """Cote un passage du F-SUS.

    Un item non chiffre est ecarte, ce qui rend le score incalculable : mieux
    vaut None qu'un score partiel qu'on prendrait pour un score complet.
    """
    cotations: dict[str, int] = {}
    for item, valeur in passage.items():
        entier = _entier(valeur)
        if entier is not None:
            cotations[item] = entier
    return score_fsus(cotations)


@dataclass(frozen=True)
class AgregatFsus:
    """Le F-SUS : par praticien, globalement, et sous forme de COURBE.

    Une moyenne unique ne distingue pas un outil qu'on apprend a aimer d'un
    outil dont on se lasse. La courbe, si — et c'est pour cela que le releve est
    repete plutot qu'unique.
    """

    ensemble: Score
    par_praticien: dict[str, Score]
    #: Un point par rang de releve, tous praticiens confondus.
    courbe: list[Score]
    #: La suite brute des scores de chaque praticien, dans l'ordre des releves.
    #: Un None y designe un releve rendu mais incotable, pas un zero.
    courbe_par_praticien: dict[str, list[float | None]]
    seuil: float = SEUIL_FSUS

    def en_dict(self) -> dict[str, object]:
        return {
            "seuil": self.seuil,
            "ensemble": self.ensemble.en_dict(),
            "par_praticien": {
                praticien: score.en_dict()
                for praticien, score in self.par_praticien.items()
            },
            "courbe": [point.en_dict() for point in self.courbe],
            "courbe_par_praticien": self.courbe_par_praticien,
        }


def agreger_fsus(reponses: list[ReponseObservee]) -> AgregatFsus:
    """Agrege les releves du F-SUS : moyenne, ecart-type et courbe."""
    releves = decouper_releves_fsus(reponses)
    par_praticien = _releves_par_praticien(releves)
    return AgregatFsus(
        ensemble=_coter_releves(releves, "Score F-SUS, tous releves"),
        par_praticien={
            praticien: _coter_releves(siens, "Score F-SUS")
            for praticien, siens in par_praticien.items()
        },
        courbe=[
            _coter_releves(
                [r for r in releves if r.rang == rang], f"Releve {rang}"
            )
            for rang in range(1, _dernier_rang(releves) + 1)
        ],
        courbe_par_praticien={
            praticien: [r.score for r in sorted(siens, key=lambda r: r.rang)]
            for praticien, siens in par_praticien.items()
        },
    )


def _releves_par_praticien(
    releves: list[ReleveFsus],
) -> dict[str, list[ReleveFsus]]:
    """Groupe des releves par praticien."""
    groupes: dict[str, list[ReleveFsus]] = {}
    for releve in releves:
        groupes.setdefault(releve.praticien_id, []).append(releve)
    return groupes


def _dernier_rang(releves: list[ReleveFsus]) -> int:
    """Rang du releve le plus avance atteint par un praticien."""
    return max((releve.rang for releve in releves), default=0)


def _coter_releves(releves: list[ReleveFsus], libelle: str) -> Score:
    """Moyenne d'un lot de releves.

    Un score incalculable n'entre dans AUCUNE moyenne, mais il est compte :
    l'ignorer en silence ferait passer un questionnaire a moitie rempli pour un
    questionnaire complet.
    """
    scores = [releve.score for releve in releves if releve.score is not None]
    return coter(scores, non_cotables=len(releves) - len(scores), libelle=libelle)


# --- Les items par cas ------------------------------------------------------


@dataclass(frozen=True)
class Repartition:
    """Les effectifs par option d'un item a choix unique.

    Chaque option porte SON taux sur le denominateur commun, et les options ne
    se somment jamais : additionner "je l'aurais omis" et "je l'aurais ecrit de
    toute facon" confondrait une affirmation de SECURITE avec un simple confort
    de redaction, et gonflerait toute la couche de completude.
    """

    libelle: str
    effectif: int
    options: dict[str, Taux]
    #: Reponses hors des options declarees : comptees, jamais escamotees.
    hors_options: int

    def en_dict(self) -> dict[str, object]:
        return {
            "libelle": self.libelle,
            "effectif": self.effectif,
            "options": {nom: taux.en_dict() for nom, taux in self.options.items()},
            "hors_options": self.hors_options,
        }


def derniere_par_dossier(reponses: list[ReponseObservee]) -> list[ReponseObservee]:
    """Une seule reponse par (praticien, dossier, item) : la DERNIERE.

    Rien n'empeche aujourd'hui un questionnaire d'etre renvoye deux fois — un
    double-clic, une reprise apres coupure. Compter les LIGNES au lieu des
    COMPTES RENDUS gonfle alors le denominateur, et sur le taux d'omission,
    qui est un critere PRINCIPAL de securite, cela suffit a publier un chiffre
    faux : deux CR questionnes dont un avec omission donnaient 2/3 au lieu de
    1/2.

    La derniere et non la premiere : si le praticien se reprend, c'est sa
    reprise qui vaut.
    """
    retenues: dict[tuple[str, str | None, str], ReponseObservee] = {}
    for reponse in reponses:
        cle = (reponse.praticien_id, reponse.dossier_id, reponse.item)
        precedente = retenues.get(cle)
        if precedente is None or reponse.repondu_a >= precedente.repondu_a:
            retenues[cle] = reponse
    return list(retenues.values())


def agreger_oui_non(
    reponses: list[ReponseObservee], questionnaire: str, item: str, libelle: str
) -> Taux:
    """Part de "oui" sur les COMPTES RENDUS ou l'item a ete repondu.

    Une reponse ni oui ni non sort des DEUX termes : la compter comme un non
    fabriquerait une securite qu'on n'a pas mesuree.
    """
    valeurs = [
        _normaliser(reponse.valeur)
        for reponse in derniere_par_dossier(
            _reponses_a(reponses, questionnaire, item)
        )
    ]
    oui = sum(1 for valeur in valeurs if valeur == _OUI)
    non = sum(1 for valeur in valeurs if valeur == _NON)
    return Taux(oui, oui + non, libelle)


def agreger_likert(
    reponses: list[ReponseObservee], questionnaire: str, item: str, libelle: str
) -> Score:
    """Moyenne d'un item cote de 1 a 5.

    Les reponses hors echelle ("Non applicable", item saute) sortent de la
    moyenne et sont comptees a part : les coter a zero ecraserait la moyenne
    d'un item ou l'option existe justement pour ne pas repondre.
    """
    lues = [
        _entier(reponse.valeur)
        for reponse in _reponses_a(reponses, questionnaire, item)
    ]
    cotees = [float(lue) for lue in lues if lue is not None and 1 <= lue <= 5]
    return coter(cotees, non_cotables=len(lues) - len(cotees), libelle=libelle)


def agreger_choix(
    reponses: list[ReponseObservee], questionnaire: str, item: str, libelle: str
) -> Repartition:
    """Repartition d'un item a choix unique sur ses options DECLAREES.

    Les options viennent du catalogue et ne sont jamais recopiees : une reponse
    dont le libelle ne figure plus au catalogue est comptee dans
    `hors_options` plutot que disparue du denominateur.
    """
    options = _options_declarees(questionnaire, item)
    valeurs = [
        reponse.valeur.strip()
        for reponse in _reponses_a(reponses, questionnaire, item)
    ]
    comptes = Counter(valeurs)
    reconnues = sum(comptes[option] for option in options)
    return Repartition(
        libelle=libelle,
        effectif=reconnues,
        options={
            option: Taux(comptes[option], reconnues, option) for option in options
        },
        hors_options=len(valeurs) - reconnues,
    )


@dataclass(frozen=True)
class AgregatParCas:
    """Ce que le praticien DECLARE, compte rendu par compte rendu.

    Tout ce qui est ici est hors d'atteinte de la telemetrie. Un oubli ne laisse
    aucune trace ; un panneau ouvert ne dit pas qu'on a compris ; une erreur que
    le systeme a affirmee sans la soumettre n'est jamais decidee, donc jamais
    tracee. Ces items n'ont pas de substitut, et c'est pour cela qu'on prend
    quarante secondes au praticien apres chaque cas.
    """

    omission: Taux
    attestation: Taux
    erreur_introduite: Taux
    comprehension: Score
    oubli_rattrape: Repartition
    preference: Repartition
    seuil_omission: float
    seuil_comprehension: float

    def en_dict(self) -> dict[str, object]:
        return {
            "omission": self.omission.en_dict(),
            "attestation": self.attestation.en_dict(),
            "erreur_introduite": self.erreur_introduite.en_dict(),
            "comprehension": self.comprehension.en_dict(),
            "oubli_rattrape": self.oubli_rattrape.en_dict(),
            "preference": self.preference.en_dict(),
            "seuil_omission": self.seuil_omission,
            "seuil_comprehension": self.seuil_comprehension,
        }


#: Seuils du protocole, section 6. Figes avant le premier cas : un seuil fixe
#: apres avoir vu les donnees ne vaut rien.
SEUIL_OMISSION: Final[float] = 0.05
SEUIL_COMPREHENSION: Final[float] = 4.0
SEUIL_HALLUCINATION: Final[float] = 0.02
SEUIL_ACCEPTATION: Final[float] = 0.60
SEUIL_UTILITE_COMPLETUDE: Final[float] = 0.70
SEUIL_CONSULTATION_JUSTIFICATIONS: Final[float] = 0.50
SEUIL_PRATICIENS_FAVORABLES: Final[float] = 8.0


def agreger_par_cas(reponses: list[ReponseObservee]) -> AgregatParCas:
    """Agrege les items declares apres chaque compte rendu."""
    return AgregatParCas(
        omission=agreger_oui_non(
            reponses, QUESTIONNAIRE_PAR_CAS, ITEM_OMISSION,
            "Comptes rendus ou une omission est signalee",
        ),
        attestation=agreger_oui_non(
            reponses, QUESTIONNAIRE_PAR_CAS, ITEM_ATTESTATION,
            "Comptes rendus que le praticien validerait en routine",
        ),
        erreur_introduite=agreger_oui_non(
            reponses, QUESTIONNAIRE_PAR_CAS, ITEM_ERREUR_INTRODUITE,
            "Comptes rendus ou une erreur du logiciel a du etre corrigee",
        ),
        comprehension=agreger_likert(
            reponses, QUESTIONNAIRE_PAR_CAS, ITEM_COMPREHENSION,
            "J'ai compris pourquoi le systeme proposait ce qu'il proposait",
        ),
        oubli_rattrape=agreger_choix(
            reponses, QUESTIONNAIRE_PAR_CAS, ITEM_OUBLI_RATTRAPE,
            "Signale quelque chose que je n'aurais pas ecrit sans lui",
        ),
        preference=agreger_choix(
            reponses, QUESTIONNAIRE_PAR_CAS, ITEM_PREFERENCE,
            "Aurais-je prefere rediger ce compte rendu",
        ),
        seuil_omission=SEUIL_OMISSION,
        seuil_comprehension=SEUIL_COMPREHENSION,
    )


def compter_praticiens_favorables(reponses: list[ReponseObservee]) -> Taux:
    """Praticiens souhaitant continuer a utiliser l'outil, une voix chacun.

    La DERNIERE reponse de chacun fait foi : le questionnaire de fin d'etude
    peut etre renvoye, et compter deux fois le meme praticien lui donnerait deux
    voix sur un critere qui se lit en praticiens, pas en reponses.
    """
    derniere: dict[str, str] = {}
    for reponse in sorted(
        _reponses_a(reponses, QUESTIONNAIRE_FIN_ETUDE, ITEM_SOUHAIT_DE_CONTINUER),
        key=_horodatage,
    ):
        derniere[reponse.praticien_id] = _normaliser(reponse.valeur)
    return Taux(
        sum(1 for voix in derniere.values() if voix == _OUI),
        len(derniere),
        "Praticiens souhaitant continuer",
    )


# --- Les agregats de dossier ------------------------------------------------


@dataclass
class DossierObserve:
    """Un compte rendu, reduit a ce dont les agregats de dossier ont besoin."""

    praticien_id: str
    session_id: str
    index_session: int
    revision_nette_ms: int | None = None
    #: Vrai des qu'une justification a ete ouverte au moins une fois sur ce cas.
    justification_consultee: bool = False


@dataclass(frozen=True)
class AgregatDossiers:
    """Les temps de revision et la consultation des justifications, par cas."""

    revision_nette: Distribution
    revision_nette_par_praticien: dict[str, Distribution]
    #: Un groupe par tiers d'ordre de passage, decoupe praticien par praticien.
    revision_nette_par_tercile: list[Distribution]
    consultation_justifications: Taux

    def en_dict(self) -> dict[str, object]:
        return {
            "revision_nette_ms": self.revision_nette.en_dict(),
            "revision_nette_ms_par_praticien": {
                praticien: distribution.en_dict()
                for praticien, distribution in
                self.revision_nette_par_praticien.items()
            },
            "revision_nette_ms_par_tercile": [
                distribution.en_dict()
                for distribution in self.revision_nette_par_tercile
            ],
            "consultation_justifications":
                self.consultation_justifications.en_dict(),
        }


def agreger_dossiers(dossiers: list[DossierObserve]) -> AgregatDossiers:
    """Agrege les temps de revision nets et la consultation des justifications."""
    return AgregatDossiers(
        revision_nette=resumer(_temps(dossiers), "Revision nette (ms)"),
        revision_nette_par_praticien={
            praticien: resumer(_temps(siens), "Revision nette (ms)")
            for praticien, siens in _dossiers_par_praticien(dossiers).items()
        },
        revision_nette_par_tercile=[
            resumer(groupe, f"Tercile {rang}")
            for rang, groupe in enumerate(_temps_par_tercile(dossiers), start=1)
        ],
        consultation_justifications=Taux(
            sum(1 for dossier in dossiers if dossier.justification_consultee),
            len(dossiers),
            "Cas ou une justification a ete ouverte",
        ),
    )


def _temps(dossiers: list[DossierObserve]) -> list[float]:
    """Les temps de revision nets disponibles, dans l'ordre recu.

    Un dossier sans horodatage complet n'a pas de duree : il sort de la serie
    plutot que d'y entrer a zero.
    """
    return [
        float(dossier.revision_nette_ms)
        for dossier in dossiers
        if dossier.revision_nette_ms is not None
    ]


def _dossiers_par_praticien(
    dossiers: list[DossierObserve],
) -> dict[str, list[DossierObserve]]:
    """Groupe des dossiers par praticien."""
    groupes: dict[str, list[DossierObserve]] = {}
    for dossier in dossiers:
        groupes.setdefault(dossier.praticien_id, []).append(dossier)
    return groupes


def _temps_par_tercile(dossiers: list[DossierObserve]) -> list[list[float]]:
    """Les temps de revision, groupes par tiers d'ordre de passage.

    Le decoupage se fait PRATICIEN PAR PRATICIEN puis se met en commun. Des
    terciles calcules sur le corpus entier melangeraient les premiers cas d'un
    praticien avec les derniers d'un autre : ils ne mesureraient plus
    l'apprentissage mais l'ordre d'arrivee des participants.
    """
    groupes: list[list[float]] = [[], [], []]
    for siens in _dossiers_par_praticien(dossiers).values():
        ordonnes = sorted(siens, key=lambda d: (d.session_id, d.index_session))
        for rang, tiers in enumerate(terciles(_temps(ordonnes))):
            groupes[rang].extend(tiers)
    return groupes


# --- Le tableau de couverture -----------------------------------------------
#
# Ce que le proprietaire regarde en premier : critere par critere, la valeur
# mesuree, le seuil du protocole, et s'il y a de quoi conclure.


RANG_PRINCIPAL: Final = "principal"
RANG_SECONDAIRE: Final = "secondaire"
RANG_EXPLORATOIRE: Final = "exploratoire"
#: Hors du tableau de la section 6, ajoute parce que rien d'autre ne le mesure.
RANG_COMPLEMENTAIRE: Final = "complementaire"

SEUIL_AU_MOINS: Final = "au_moins"
SEUIL_AU_PLUS: Final = "au_plus"
SEUIL_DESCRIPTIF: Final = "descriptif"

UNITE_TAUX: Final = "taux"
UNITE_SCORE: Final = "score"
UNITE_EFFECTIF: Final = "effectif"
UNITE_MS: Final = "ms"

#: Effectifs en dessous desquels un chiffre ne se conclut pas.
#:
#: Ce ne sont PAS des seuils de jugement — ceux-la sont figes par le protocole —
#: mais des seuils de lisibilite, declares d'avance pour la meme raison : decider
#: apres coup qu'un effectif suffisait revient a choisir sa conclusion.
#:
#: Le protocole dimensionne l'etude a 2 000 propositions, ou un taux de 2 %
#: s'estime a plus ou moins 0,6 point. A 200, l'intervalle de ce meme taux couvre
#: encore le seuil de securite : en dessous, aucun sens ne se conclut.
EFFECTIF_MINIMAL_PROPOSITIONS: Final[int] = 200
#: Un critere par compte rendu vise 25 cas par praticien : sous un praticien
#: complet, on lit la variabilite d'un seul operateur.
EFFECTIF_MINIMAL_DOSSIERS: Final[int] = 25
#: Le F-SUS est releve tous les cinq comptes rendus. Dix releves, c'est deux
#: praticiens alles au bout ; en dessous, un seul releve deplace la moyenne de
#: plus de cinq points, soit davantage que l'ecart au seuil qu'on veut lire.
EFFECTIF_MINIMAL_RELEVES: Final[int] = 10
#: Le critere "8 sur 10" ne se lit pas sur moins de dix praticiens inclus.
EFFECTIF_MINIMAL_PRATICIENS: Final[int] = 10


@dataclass(frozen=True)
class Critere:
    """Un critere de jugement du protocole, face a ce que l'etude a mesure.

    `atteint` et `donnees_suffisantes` sont DEUX questions distinctes, et les
    confondre est la faute que ce tableau existe pour eviter. Une valeur peut
    etre du bon cote du seuil sur deux observations : le tableau dit alors
    "atteint" ET "pas de quoi conclure", parce que les deux sont vrais.
    """

    cle: str
    libelle: str
    rang: str
    unite: str
    valeur: float | None
    seuil: float | None
    sens: str
    effectif: int
    effectif_minimal: int
    note: str = ""
    #: Le NUMERATEUR est-il seulement observable ?
    #:
    #: Troisieme etat, distinct de `atteint` et de `donnees_suffisantes`, et
    #: sans lui on publie le pire des chiffres : un zero confiant sur une
    #: question que personne n'a posee. Cas reel — tant que l'interface ne
    #: demandait pas la nature d'une correction, le taux d'erreurs de fond
    #: valait 0,0 sur des centaines de corrections, et le tableau annoncait
    #: "donnees suffisantes : oui".
    #:
    #: Un denominateur peut etre large et le numerateur inobservable : ce sont
    #: deux questions differentes, et les confondre fabrique de la fausse
    #: securite.
    observable: bool = True

    @property
    def donnees_suffisantes(self) -> bool:
        """Y a-t-il de quoi conclure sur ce critere ?"""
        return (
            self.observable
            and self.valeur is not None
            and self.effectif >= self.effectif_minimal
        )

    @property
    def atteint(self) -> bool | None:
        """Du bon cote du seuil ? None quand il n'y a rien a comparer."""
        if self.valeur is None or self.seuil is None:
            return None
        if self.sens == SEUIL_AU_MOINS:
            return self.valeur >= self.seuil
        if self.sens == SEUIL_AU_PLUS:
            return self.valeur <= self.seuil
        return None

    def en_dict(self) -> dict[str, object]:
        return {
            "cle": self.cle,
            "libelle": self.libelle,
            "rang": self.rang,
            "unite": self.unite,
            "valeur": self.valeur,
            "seuil": self.seuil,
            "sens": self.sens,
            "effectif": self.effectif,
            "effectif_minimal": self.effectif_minimal,
            "atteint": self.atteint,
            "observable": self.observable,
            "donnees_suffisantes": self.donnees_suffisantes,
            "note": self.note,
        }


def couverture(
    propositions: IndicateursPropositions,
    fsus: AgregatFsus,
    par_cas: AgregatParCas,
    dossiers: AgregatDossiers,
    praticiens_favorables: Taux,
) -> list[Critere]:
    """Assemble le tableau de couverture des criteres du protocole.

    Il est calcule sur TOUTES les decisions et non hors decisions hatives : les
    seuils du protocole portent sur ce que l'etude a reellement recueilli. Le
    depouillement publie l'autre lecture a cote, et l'ecart entre les deux se
    lit la.
    """
    return [
        *_criteres_de_securite(propositions, par_cas),
        *_criteres_d_acceptabilite(propositions, fsus, praticiens_favorables),
        *_criteres_secondaires(propositions, par_cas, dossiers),
        *_criteres_complementaires(propositions, par_cas),
        *_criteres_exploratoires(propositions, dossiers),
    ]


def _criteres_de_securite(
    propositions: IndicateursPropositions, par_cas: AgregatParCas
) -> list[Critere]:
    """Les criteres principaux de securite (protocole section 6)."""
    non_ancrees = propositions.acceptation_non_ancree
    return [
        Critere(
            cle="propositions_non_soutenues",
            libelle="Propositions non soutenues par la dictee",
            rang=RANG_PRINCIPAL,
            unite=UNITE_TAUX,
            valeur=propositions.hallucination.valeur,
            seuil=SEUIL_HALLUCINATION,
            sens=SEUIL_AU_PLUS,
            effectif=propositions.hallucination.denominateur,
            effectif_minimal=EFFECTIF_MINIMAL_PROPOSITIONS,
            note="Reference externe : environ 1,5 % dans la litterature.",
        ),
        Critere(
            cle="non_soutenues_acceptees",
            libelle="Propositions non ancrees acceptees telles quelles",
            rang=RANG_PRINCIPAL,
            unite=UNITE_EFFECTIF,
            valeur=float(non_ancrees.numerateur),
            seuil=0.0,
            sens=SEUIL_AU_PLUS,
            effectif=propositions.acceptation_sans_modification.denominateur,
            effectif_minimal=EFFECTIF_MINIMAL_PROPOSITIONS,
            note=(
                "Critere bloquant, qui ne se compense pas. La portee "
                "therapeutique n'est pas codee en base : ce compte est la liste "
                "a relire une par une, pas un verdict."
            ),
        ),
        Critere(
            cle="omissions_signalees",
            libelle="Comptes rendus ou une omission est signalee",
            rang=RANG_PRINCIPAL,
            unite=UNITE_TAUX,
            valeur=par_cas.omission.valeur,
            seuil=SEUIL_OMISSION,
            sens=SEUIL_AU_PLUS,
            effectif=par_cas.omission.denominateur,
            effectif_minimal=EFFECTIF_MINIMAL_DOSSIERS,
            note=(
                "Seule mesure que la telemetrie ne peut pas produire : un oubli "
                "ne laisse aucune trace."
            ),
        ),
    ]


def _criteres_d_acceptabilite(
    propositions: IndicateursPropositions,
    fsus: AgregatFsus,
    praticiens_favorables: Taux,
) -> list[Critere]:
    """Les criteres principaux d'acceptabilite et d'ergonomie."""
    return [
        Critere(
            cle="acceptation_sans_modification",
            libelle="Acceptation sans modification",
            rang=RANG_PRINCIPAL,
            unite=UNITE_TAUX,
            valeur=propositions.acceptation_sans_modification.valeur,
            seuil=SEUIL_ACCEPTATION,
            sens=SEUIL_AU_MOINS,
            effectif=propositions.acceptation_sans_modification.denominateur,
            effectif_minimal=EFFECTIF_MINIMAL_PROPOSITIONS,
            note="Reference externe : 58 % sur un deploiement hospitalier.",
        ),
        Critere(
            cle="score_fsus",
            libelle="Score F-SUS moyen",
            rang=RANG_PRINCIPAL,
            unite=UNITE_SCORE,
            valeur=fsus.ensemble.moyenne,
            # Le seuil de 68 vaut pour l'instrument PUBLIE. Une traduction
            # interne mesure la meme chose de facon coherente avec elle-meme —
            # la courbe dans le temps reste exploitable — mais la confronter au
            # seuil reviendrait a comparer deux instruments differents. On
            # retire donc le seuil plutot que d'annoncer un depassement qui ne
            # se defendrait pas devant un relecteur.
            seuil=fsus.seuil if fsus_comparable() else None,
            sens=SEUIL_AU_MOINS,
            effectif=fsus.ensemble.effectif,
            effectif_minimal=EFFECTIF_MINIMAL_RELEVES,
            note=(
                "L'effectif compte des RELEVES, pas des praticiens : le score "
                "est repose tous les cinq comptes rendus."
                + (
                    ""
                    if fsus_comparable()
                    else " TRADUCTION INTERNE : le score compare les releves "
                    "entre eux, il ne se compare pas au seuil de 68 ni aux "
                    "scores publies. Remplacer les libelles par ceux du F-SUS "
                    "valide (Gronier et Baudet, 2021) leve cette reserve."
                )
            ),
        ),
        Critere(
            cle="praticiens_souhaitant_continuer",
            libelle="Praticiens souhaitant continuer",
            rang=RANG_PRINCIPAL,
            unite=UNITE_EFFECTIF,
            valeur=float(praticiens_favorables.numerateur),
            seuil=SEUIL_PRATICIENS_FAVORABLES,
            sens=SEUIL_AU_MOINS,
            effectif=praticiens_favorables.denominateur,
            effectif_minimal=EFFECTIF_MINIMAL_PRATICIENS,
            note="Une voix par praticien : la derniere reponse de chacun fait foi.",
        ),
    ]


def _criteres_secondaires(
    propositions: IndicateursPropositions,
    par_cas: AgregatParCas,
    dossiers: AgregatDossiers,
) -> list[Critere]:
    """Les criteres secondaires du protocole."""
    return [
        Critere(
            cle="utilite_completude",
            libelle="Suggestions de completude jugees pertinentes",
            rang=RANG_SECONDAIRE,
            unite=UNITE_TAUX,
            valeur=propositions.utilite_completude.valeur,
            seuil=SEUIL_UTILITE_COMPLETUDE,
            sens=SEUIL_AU_MOINS,
            effectif=propositions.utilite_completude.denominateur,
            effectif_minimal=EFFECTIF_MINIMAL_PROPOSITIONS,
            note=(
                "\"Pertinent mais non retenu\" compte au numerateur : c'est une "
                "decision editoriale du praticien, pas un faux positif."
            ),
        ),
        Critere(
            cle="justifications_consultees",
            libelle="Cas ou une justification a ete ouverte",
            rang=RANG_SECONDAIRE,
            unite=UNITE_TAUX,
            valeur=dossiers.consultation_justifications.valeur,
            seuil=SEUIL_CONSULTATION_JUSTIFICATIONS,
            sens=SEUIL_AU_MOINS,
            effectif=dossiers.consultation_justifications.denominateur,
            effectif_minimal=EFFECTIF_MINIMAL_DOSSIERS,
        ),
        Critere(
            cle="comprehension",
            libelle="J'ai compris pourquoi le systeme proposait ce qu'il proposait",
            rang=RANG_SECONDAIRE,
            unite=UNITE_SCORE,
            valeur=par_cas.comprehension.moyenne,
            seuil=par_cas.seuil_comprehension,
            sens=SEUIL_AU_MOINS,
            effectif=par_cas.comprehension.effectif,
            effectif_minimal=EFFECTIF_MINIMAL_DOSSIERS,
            note=(
                "Explicabilite DECLAREE, sans substitut : aucune telemetrie ne "
                "dit si le praticien a compris, seulement s'il a ouvert un "
                "panneau."
            ),
        ),
        Critere(
            cle="abstention_codes",
            libelle="Codes : je ne sais pas",
            rang=RANG_SECONDAIRE,
            unite=UNITE_TAUX,
            valeur=propositions.abstention_codes.valeur,
            seuil=None,
            sens=SEUIL_DESCRIPTIF,
            effectif=propositions.abstention_codes.denominateur,
            effectif_minimal=EFFECTIF_MINIMAL_PROPOSITIONS,
            note="Descriptif au protocole : un taux eleve dit la lisibilite des codes.",
        ),
    ]


def _criteres_complementaires(
    propositions: IndicateursPropositions, par_cas: AgregatParCas
) -> list[Critere]:
    """Ce qui n'est pas au tableau de la section 6 et que rien d'autre ne mesure."""
    corrections = propositions.corrections
    omis = par_cas.oubli_rattrape.options.get(
        _option(QUESTIONNAIRE_PAR_CAS, ITEM_OUBLI_RATTRAPE, 0)
    )
    avec = par_cas.preference.options.get(
        _option(QUESTIONNAIRE_PAR_CAS, ITEM_PREFERENCE, 0)
    )
    return [
        Critere(
            cle="justesse_sur_le_fond",
            libelle="Justesse sur le fond (conforme ou corrige en style)",
            rang=RANG_COMPLEMENTAIRE,
            unite=UNITE_TAUX,
            valeur=corrections.justesse_sur_le_fond.valeur,
            seuil=None,
            sens=SEUIL_DESCRIPTIF,
            effectif=corrections.justesse_sur_le_fond.denominateur,
            effectif_minimal=EFFECTIF_MINIMAL_PROPOSITIONS,
            note=(
                "Separe \"le systeme s'est trompe\" de \"j'ecris autrement\". "
                "Une correction de precision n'y entre pas : le fond etait juste "
                "mais incomplet."
            ),
        ),
        Critere(
            cle="corrections_pour_erreur_de_fond",
            libelle="Corrections imputant une erreur de fond au systeme",
            rang=RANG_COMPLEMENTAIRE,
            unite=UNITE_TAUX,
            valeur=corrections.erreur_fond.valeur,
            seuil=None,
            sens=SEUIL_DESCRIPTIF,
            effectif=corrections.erreur_fond.denominateur,
            effectif_minimal=EFFECTIF_MINIMAL_PROPOSITIONS,
            # Si AUCUNE nature n'a ete declaree, le numerateur n'est pas
            # observable : le taux vaut zero parce que la question n'a pas ete
            # posee, pas parce que le systeme ne s'est jamais trompe. Publier ce
            # zero comme une mesure serait le plus grave des faux signaux.
            observable=(
                corrections.non_declaree.numerateur < corrections.corrigees
            ),
            note=(
                f"{corrections.non_declaree.numerateur} correction(s) sur "
                f"{corrections.corrigees} sans nature declaree : elles "
                "n'imputent rien a personne et restent au denominateur."
            ),
        ),
        Critere(
            cle="erreur_introduite",
            libelle="Comptes rendus ou une erreur du logiciel a du etre corrigee",
            rang=RANG_COMPLEMENTAIRE,
            unite=UNITE_TAUX,
            valeur=par_cas.erreur_introduite.valeur,
            seuil=None,
            sens=SEUIL_DESCRIPTIF,
            effectif=par_cas.erreur_introduite.denominateur,
            effectif_minimal=EFFECTIF_MINIMAL_DOSSIERS,
            note=(
                "Le point aveugle : une erreur que le systeme a AFFIRMEE sans la "
                "soumettre echappe a toute decision, donc a toute telemetrie."
            ),
        ),
        Critere(
            cle="attestation",
            libelle="Comptes rendus que le praticien validerait en routine",
            rang=RANG_COMPLEMENTAIRE,
            unite=UNITE_TAUX,
            valeur=par_cas.attestation.valeur,
            seuil=None,
            sens=SEUIL_DESCRIPTIF,
            effectif=par_cas.attestation.denominateur,
            effectif_minimal=EFFECTIF_MINIMAL_DOSSIERS,
            note=(
                "Un compte rendu valide dans une etude mais qu'on ne signerait "
                "pas en routine ne prouve rien."
            ),
        ),
        Critere(
            cle="oubli_rattrape",
            libelle="Comptes rendus ou le praticien declare qu'il aurait omis",
            rang=RANG_COMPLEMENTAIRE,
            unite=UNITE_TAUX,
            valeur=omis.valeur if omis is not None else None,
            seuil=None,
            sens=SEUIL_DESCRIPTIF,
            effectif=par_cas.oubli_rattrape.effectif,
            effectif_minimal=EFFECTIF_MINIMAL_DOSSIERS,
            note=(
                "Ne jamais additionner avec \"je l'aurais ecrit de toute facon\" : "
                "l'un est une affirmation de securite, l'autre un confort."
            ),
        ),
        Critere(
            cle="preference_avec_le_logiciel",
            libelle="Comptes rendus que le praticien aurait prefere rediger avec",
            rang=RANG_COMPLEMENTAIRE,
            unite=UNITE_TAUX,
            valeur=avec.valeur if avec is not None else None,
            seuil=None,
            sens=SEUIL_DESCRIPTIF,
            effectif=par_cas.preference.effectif,
            effectif_minimal=EFFECTIF_MINIMAL_DOSSIERS,
            note=(
                "L'item qui porte la conclusion sous la seule forme que le "
                "praticien reconnaitrait comme la sienne."
            ),
        ),
        Critere(
            cle="taux_de_soumission_college",
            libelle="Taux de soumission du college",
            rang=RANG_COMPLEMENTAIRE,
            unite=UNITE_TAUX,
            valeur=None,
            seuil=None,
            sens=SEUIL_DESCRIPTIF,
            effectif=0,
            effectif_minimal=EFFECTIF_MINIMAL_DOSSIERS,
            note=(
                "NON DEPOUILLABLE EN L'ETAT : le taux est calcule a chaque "
                "generation (trace du moteur, cle taux_de_soumission) mais rien "
                "ne le conserve en base. Le reconstruire depuis le compte rendu "
                "donnerait un chiffre faux, puisque les assertions AFFIRMEES ne "
                "sont volontairement pas enregistrees. Une absence de mesure "
                "n'est pas un zero."
            ),
        ),
    ]


def _criteres_exploratoires(
    propositions: IndicateursPropositions, dossiers: AgregatDossiers
) -> list[Critere]:
    """Les criteres exploratoires : jamais de seuil, jamais de conclusion."""
    return [
        Critere(
            cle="temps_revision_net",
            libelle="Temps de revision net, mediane (ms)",
            rang=RANG_EXPLORATOIRE,
            unite=UNITE_MS,
            valeur=dossiers.revision_nette.mediane,
            seuil=None,
            sens=SEUIL_DESCRIPTIF,
            effectif=dossiers.revision_nette.effectif,
            effectif_minimal=EFFECTIF_MINIMAL_DOSSIERS,
            note=(
                "Aucun critere de temps absolu au protocole. Mediane et non "
                "moyenne : une interruption longue ecrase une moyenne."
            ),
        ),
        Critere(
            cle="changement_apres_justification",
            libelle="Avis change apres ouverture de la justification",
            rang=RANG_EXPLORATOIRE,
            unite=UNITE_TAUX,
            valeur=propositions.changement_apres_justification.valeur,
            seuil=None,
            sens=SEUIL_DESCRIPTIF,
            effectif=propositions.changement_apres_justification.denominateur,
            effectif_minimal=EFFECTIF_MINIMAL_PROPOSITIONS,
        ),
        Critere(
            cle="decisions_hatives",
            libelle="Decisions plus rapides que le temps de lecture",
            rang=RANG_EXPLORATOIRE,
            unite=UNITE_TAUX,
            valeur=propositions.decisions_hatives.valeur,
            seuil=None,
            sens=SEUIL_DESCRIPTIF,
            effectif=propositions.decisions_hatives.denominateur,
            effectif_minimal=EFFECTIF_MINIMAL_PROPOSITIONS,
            note=(
                "Proxy du biais d'automatisation. Un ecart important avec la "
                "lecture hors hatives invalide la lecture naive des taux."
            ),
        ),
    ]


# --- La synthese complete ---------------------------------------------------


@dataclass(frozen=True)
class Synthese:
    """Tout ce que l'etude sait dire d'elle-meme a cet instant."""

    couverture: list[Critere]
    propositions: Depouillement
    fsus: AgregatFsus
    par_cas: AgregatParCas
    dossiers: AgregatDossiers
    praticiens_favorables: Taux

    def en_dict(self) -> dict[str, object]:
        # La couverture vient EN TETE : elle dit ou en est l'etude avant de dire
        # ce qu'elle trouve, et c'est dans cet ordre qu'un tableau se lit.
        return {
            "couverture": [critere.en_dict() for critere in self.couverture],
            "propositions": self.propositions.en_dict(),
            "fsus": self.fsus.en_dict(),
            "par_cas": self.par_cas.en_dict(),
            "dossiers": self.dossiers.en_dict(),
            "praticiens_favorables": self.praticiens_favorables.en_dict(),
        }


def synthetiser(
    decisions: list[DecisionObservee],
    reponses: list[ReponseObservee],
    dossiers: list[DossierObserve],
) -> Synthese:
    """Assemble les indicateurs de l'etude et leur tableau de couverture."""
    depouillement = depouiller(decisions)
    resultats_fsus = agreger_fsus(reponses)
    resultats_par_cas = agreger_par_cas(reponses)
    resultats_dossiers = agreger_dossiers(dossiers)
    favorables = compter_praticiens_favorables(reponses)
    return Synthese(
        couverture=couverture(
            depouillement.toutes,
            resultats_fsus,
            resultats_par_cas,
            resultats_dossiers,
            favorables,
        ),
        propositions=depouillement,
        fsus=resultats_fsus,
        par_cas=resultats_par_cas,
        dossiers=resultats_dossiers,
        praticiens_favorables=favorables,
    )
