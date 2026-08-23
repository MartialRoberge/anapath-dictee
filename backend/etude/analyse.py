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

Reference : docs/specs/etude/Protocole_etude_MARC.md.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field

from etude.vocabulaire import TYPE_CODE, TYPE_COMPLETUDE, TYPE_RESTITUTION


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
                )
            },
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
