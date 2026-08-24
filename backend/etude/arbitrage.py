"""Arbitrage du college : que soumet-on au praticien, et que tait-on ?

LA REGLE, reprise de la politique de questions et etendue aux propositions :

    On ne soumet a validation que ce dont la decision CHANGE QUELQUE CHOSE.
    L'incertitude n'est pas un motif suffisant ; seule l'incertitude qui change
    quelque chose l'est.

Le nombre de propositions n'est donc pas un objectif — c'est une consequence.
Un compte rendu limpide, ou les trois relecteurs sont d'accord et ou chaque
assertion est ancree dans la dictee, doit produire PEU de propositions. C'est le
bon comportement, pas une sous-performance : chaque proposition superflue coute
une verification, et un praticien a qui l'on fait tout verifier finit par ne
plus rien verifier.

TROIS COMPORTEMENTS, JAMAIS CONFONDUS

    AFFIRMER    le college est unanime et la citation tient  -> silence
    PROPOSER    les relecteurs divergent, ou tous refusent   -> un geste
    S'ABSTENIR  rien ne permet de trancher                   -> ni texte ni question

LE VERROU CONTRE LE COLLEGE LUI-MEME

Un relecteur affirme qu'une assertion est soutenue et cite un passage. Cette
citation est cherchee dans la dictee, ICI, par correspondance exacte. Si elle
ne s'y trouve pas, le relecteur a fabrique sa preuve : son vote bascule en NON
SOUTENU, quoi qu'il ait repondu. Sans ce verrou, ajouter des relecteurs
ajouterait des hallucinations au lieu d'en retirer.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Final

from etude.ancrage import Empan, decouper
from reports.college import Avis, Manque, RapportCollege

# --- Comportements ---------------------------------------------------------

AFFIRMER: Final = "affirmer"
PROPOSER: Final = "proposer"
ABSTENIR: Final = "abstenir"

#: Motifs de soumission, pour l'affichage et le depouillement.
MOTIF_DESACCORD: Final = "desaccord"
MOTIF_REFUS_UNANIME: Final = "refus_unanime"
MOTIF_CITATION_INTROUVABLE: Final = "citation_introuvable"
MOTIF_QUORUM: Final = "quorum_insuffisant"

#: En dessous de deux voix, il n'y a pas de college : un avis unique n'est pas
#: un consensus. On soumet alors par prudence plutot que d'affirmer sur une voix.
QUORUM_MINIMAL: Final[int] = 2


@dataclass(frozen=True)
class Soumission:
    """Le sort d'une assertion apres arbitrage.

    `voix_pour` et `voix_total` sont la confiance AFFICHABLE : ce n'est pas un
    score de modele — mal calibre et impossible a expliquer — mais un decompte.
    "Deux relecteurs sur trois ont retrouve ce passage dans votre dictee" se
    verifie ; un 0,73 ne se verifie pas.
    """

    rang: int
    assertion: str
    comportement: str
    motif: str
    voix_pour: int
    voix_total: int
    empan: Empan | None = None
    #: Une phrase par lentille, dans l'ordre des lentilles. C'est la
    #: justification affichee au praticien, et elle n'est pas generee pour lui :
    #: c'est ce que les relecteurs ont reellement ecrit en jugeant.
    justifications: tuple[str, ...] = ()


@dataclass
class Arbitrage:
    """Le resultat complet, prêt a etre affiche et a etre mesure."""

    soumissions: list[Soumission] = field(default_factory=list)
    manques: list[Manque] = field(default_factory=list)

    @property
    def a_valider(self) -> list[Soumission]:
        return [s for s in self.soumissions if s.comportement == PROPOSER]

    @property
    def affirmees(self) -> list[Soumission]:
        return [s for s in self.soumissions if s.comportement == AFFIRMER]


def verifier_citation(citation: str, transcription: str) -> Empan | None:
    """La citation existe-t-elle vraiment dans la dictee ?

    Correspondance sur les JETONS NORMALISES et non sur la chaine brute : un
    modele recopie a la ponctuation et a la casse pres, et exiger l'octet exact
    rejetterait des citations honnetes. La suite de mots, elle, doit etre
    exactement celle de la dictee — sinon ce n'est plus une citation.
    """
    jetons_citation = [j.forme for j in decouper(citation)]
    if len(jetons_citation) < 2:
        # Un mot isole n'est pas une citation : il se retrouve partout et ne
        # prouve rien sur le contexte.
        return None

    jetons_source = decouper(transcription)
    formes = [j.forme for j in jetons_source]
    taille = len(jetons_citation)

    for depart in range(len(formes) - taille + 1):
        if formes[depart:depart + taille] == jetons_citation:
            debut = jetons_source[depart].debut
            fin = jetons_source[depart + taille - 1].fin
            return Empan(
                debut=debut,
                fin=fin,
                extrait=transcription[debut:fin],
                recouvrement=1.0,
            )
    return None


def _voix(avis: list[Avis], transcription: str) -> tuple[int, Empan | None, bool]:
    """Depouille les voix d'une assertion.

    Retourne le nombre de voix POUR, le meilleur empan trouve, et si une
    citation a ete invalidee. Une voix POUR dont la citation est introuvable ne
    compte pas : c'est le verrou contre le college lui-meme.
    """
    pour = 0
    empan: Empan | None = None
    citation_fabriquee = False

    for un_avis in avis:
        if not un_avis.soutenue:
            continue
        trouve = verifier_citation(un_avis.citation, transcription) if un_avis.citation else None
        if trouve is None:
            citation_fabriquee = True
            continue
        pour += 1
        if empan is None or (trouve.fin - trouve.debut) < (empan.fin - empan.debut):
            # A egalite on garde l'empan le plus court : il designe plus
            # precisement, donc il se relit plus vite.
            empan = trouve

    return pour, empan, citation_fabriquee


def _justifications(avis: list[Avis]) -> tuple[str, ...]:
    """Les motifs reellement ecrits, sans reformulation ET SANS PREFIXE.

    Le nom de la lentille etait colle devant chaque motif — « litteraliste :
    ... », « sceptique : ... ». Ces mots arrivaient tels quels sous les yeux du
    praticien, qui n'a aucune raison de savoir comment MARC est construit :
    « litteraliste » et « sceptique » ne veulent rien dire pour lui et donnent
    l'impression d'une machinerie qui parle d'elle-meme au lieu d'expliquer.

    Le motif seul dit le pourquoi. La lentille reste dans `avis`, pour l'etude
    et le depouillement, ou elle a un sens.

    Les doublons sont retires : deux lentilles ecrivent souvent la meme chose,
    et l'afficher deux fois donne a croire a deux raisons distinctes.
    """
    vus: set[str] = set()
    motifs: list[str] = []
    for un_avis in avis:
        motif = (un_avis.motif or "").strip()
        if not motif:
            continue
        cle = motif.casefold()
        if cle in vus:
            continue
        vus.add(cle)
        motifs.append(motif)
    return tuple(motifs)


def _trancher(
    rang: int,
    assertion: str,
    avis: list[Avis],
    transcription: str,
    quorum: int,
) -> Soumission:
    """Applique la regle a une assertion."""
    pour, empan, citation_fabriquee = _voix(avis, transcription)
    total = len(avis)
    justifications = _justifications(avis)

    def _soumission(comportement: str, motif: str) -> Soumission:
        return Soumission(
            rang=rang,
            assertion=assertion,
            comportement=comportement,
            motif=motif,
            voix_pour=pour,
            voix_total=total,
            empan=empan,
            justifications=justifications,
        )

    if total < QUORUM_MINIMAL or quorum < QUORUM_MINIMAL:
        # Pas de college : un avis unique n'est pas un consensus. On soumet
        # plutot que d'affirmer sur une voix — une panne de relecteur ne doit
        # pas se traduire par une affirmation plus confiante.
        return _soumission(PROPOSER, MOTIF_QUORUM)

    if pour == 0:
        # Personne ne retrouve l'assertion dans la dictee : c'est la candidate
        # hallucination, la proposition la plus precieuse de l'etude.
        motif = MOTIF_CITATION_INTROUVABLE if citation_fabriquee else MOTIF_REFUS_UNANIME
        return _soumission(PROPOSER, motif)

    if pour == total:
        # Unanimite, citations verifiees : demander au praticien de confirmer ce
        # que trois relecteurs ont deja verifie, c'est lui faire perdre un geste
        # et diluer son attention sur ce qui compte.
        return _soumission(AFFIRMER, "unanimite")

    return _soumission(PROPOSER, MOTIF_DESACCORD)


def arbitrer(
    rapport: RapportCollege, assertions: list[str], transcription: str
) -> Arbitrage:
    """Decide, pour chaque assertion, entre affirmer et soumettre."""
    par_rang: dict[int, list[Avis]] = {}
    for un_avis in rapport.avis:
        par_rang.setdefault(un_avis.rang, []).append(un_avis)

    arbitrage = Arbitrage(manques=list(rapport.manques))
    for rang, assertion in enumerate(assertions, start=1):
        arbitrage.soumissions.append(
            _trancher(rang, assertion, par_rang.get(rang, []), transcription, rapport.quorum)
        )
    return arbitrage


def taux_de_soumission(arbitrage: Arbitrage) -> float | None:
    """Part des assertions soumises au praticien.

    C'est l'indicateur a suivre, et il doit BAISSER quand le systeme s'ameliore.
    Un taux qui monte ne dit pas que l'outil est prudent : il dit que ses
    relecteurs ne s'accordent pas, donc que la redaction est fragile.
    """
    if not arbitrage.soumissions:
        return None
    return round(len(arbitrage.a_valider) / len(arbitrage.soumissions), 4)
