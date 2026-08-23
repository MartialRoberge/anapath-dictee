"""Decoupage d'un compte rendu en propositions validables.

La proposition est l'unite d'analyse de l'etude : c'est elle qu'on compte, pas
le compte rendu. Un CR accepte en bloc ne dit rien ; les memes phrases jugees
une a une disent lesquelles le moteur a eu raison de proposer.

D'OU VIENNENT LES PROPOSITIONS DE RESTITUTION

Du COLLEGE quand il a siege, du decoupage sinon. Ce n'est pas un detail
d'implementation, c'est la regle centrale : le decoupage sait separer les
assertions, il ne sait pas dire laquelle merite une verification. Il les propose
donc toutes, et un praticien a qui l'on fait tout verifier finit par ne plus
rien verifier. Le college, lui, tranche assertion par assertion (voir
etude/arbitrage.py) : ce que trois relecteurs affirment a l'unanimite, citations
verifiees, ne devient PAS une proposition. LE NOMBRE DE PROPOSITIONS N'EST PAS
UN OBJECTIF — un compte rendu limpide doit en produire peu, et c'est le bon
comportement.

Le decoupage reste, et il sert deux fois : il NUMEROTE les assertions soumises
au college (les trois lentilles jugent la meme liste), et il tient lieu de VOIE
DE REPLI quand le college n'a pas siege — option coupee ou fournisseur en
panne. L'etude ne s'arrete pas parce qu'un relecteur ne repond pas.

Trois filtres, dans cet ordre, et chacun protege un chiffre publie :

1. Ce qui est une COPIE LITTERALE de la dictee n'est pas une proposition, c'est
   une transcription. La compter gonflerait le taux d'acceptation avec des
   evidences que personne n'a eu a juger.
2. Ce qui n'est pas une ASSERTION CLINIQUE ne se valide pas : un commentaire
   de machine, un en-tete de section, un gabarit conditionnel.
3. Ce qui deborde le BUDGET n'est pas affiche : au-dela d'une vingtaine de
   decisions, le praticien clique sans lire et l'on mesure sa fatigue.

Une assertion clinique SANS appui dans la dictee n'est PAS supprimee. Mesure
sur cinq cas reels : la supprimer faisait disparaitre "absence de metastase
ganglionnaire (pN0)", "absence de cellules malignes", "la bronche et les
vaisseaux de section sont sains" — c'est-a-dire exactement les affirmations
qu'une hallucination rendrait dangereuses. La regle "pas d'empan, pas de
proposition" protege l'affichage contre du bruit ; appliquee ici en suppression
seche, elle effacait la mesure centrale de l'etude. Ces propositions sont donc
conservees, marquees `ancree=False`, et l'interface doit dire franchement
qu'aucun passage de la dictee ne les soutient — la question posee au praticien
devient alors simplement : l'avez-vous dit ?

Reference : docs/specs/spec/MARC_cahier_de_recueil.md section 7.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from dataclasses import dataclass, replace
from typing import Final

from etude.ancrage import Empan, ancrer, decouper, est_copie_litterale
from etude.arbitrage import (
    MOTIF_CITATION_INTROUVABLE,
    MOTIF_REFUS_UNANIME,
    PROPOSER,
)
from etude.vocabulaire import TYPE_CODE, TYPE_COMPLETUDE, TYPE_RESTITUTION
from reports.college import Avis, RapportCollege

# --- Budget d'attention ---------------------------------------------------

#: Au-dela, le praticien decide sans lire : les decisions deviennent du bruit
#: et le taux d'acceptation ne mesure plus que la fatigue.
BUDGET_MAX: Final[int] = 20

#: En dessous, l'echantillon par cas est trop maigre pour etre exploitable ;
#: c'est un signal de sous-extraction, pas une erreur.
BUDGET_CIBLE_MIN: Final[int] = 8

#: Une assertion plus courte ne porte pas de contenu clinique jugeable.
MIN_MOTS_ASSERTION: Final[int] = 4

# --- Reperage de la structure du compte rendu -----------------------------

_ENTETE: Final[re.Pattern[str]] = re.compile(
    r"^\s*(?:#{1,6}\s*|(?:\*\*|__))?\s*([A-Za-zÀ-ÿ'’ ()-]{3,40})\s*:?\s*(?:\*\*|__)?\s*$"
)

_ENTETE_INLINE: Final[re.Pattern[str]] = re.compile(
    r"^\s*(?:\*\*|__)\s*([A-Za-zÀ-ÿ'’ ()-]{3,40})\s*:\s*(?:\*\*|__)\s*(.+)$"
)

_PUCE: Final[re.Pattern[str]] = re.compile(r"^\s*(?:[-*•–]|\d+[.)])\s+")

_A_COMPLETER: Final[re.Pattern[str]] = re.compile(
    r"\[a\s*completer[^\]]*\]", re.IGNORECASE
)

_MARQUAGE: Final[re.Pattern[str]] = re.compile(r"(?:\*\*|__|\*|_|`)")

#: Commentaires que le moteur s'adresse a lui-meme, et gabarits conditionnels.
#: Ce ne sont pas des affirmations sur le cas : les faire juger ferait perdre
#: une decision et brouillerait le taux d'hallucination.
_META: Final[re.Pattern[str]] = re.compile(
    r"\[\s*(?:verifier|a\s*completer|note)\b|^\s*note\s*:|\bsi\s+realise\b",
    re.IGNORECASE,
)

#: Une ligne qui n'est qu'une etiquette de bloc ("2) Lavage broncho-alveolaire",
#: "Tumeur : blocs 11 a 13") organise le document, elle n'affirme rien.
_ETIQUETTE: Final[re.Pattern[str]] = re.compile(
    r"^\s*(?:\d+[.)]\s*)?[A-Za-zÀ-ÿ'’ ()-]{3,40}\s*:\s*(?:blocs?\b|\d)",
    re.IGNORECASE,
)

_FIN_PHRASE: Final[re.Pattern[str]] = re.compile(r"(?<=[.;:])\s+(?=[A-ZÀ-Þ])")

#: Poids clinique par section : a budget serre, on garde ce qui engage le plus.
#: La conclusion porte le diagnostic, la microscopie le raisonnement, la
#: macroscopie de la description souvent recopiee.
_PRIORITE_SECTION: Final[dict[str, int]] = {
    "conclusion": 0,
    "diagnostic": 0,
    "synthese": 1,
    "microscopie": 2,
    "examen microscopique": 2,
    "histologie": 2,
    "immunohistochimie": 3,
    "macroscopie": 4,
    "examen macroscopique": 4,
    "renseignements cliniques": 6,
    "technique": 7,
}

_PRIORITE_DEFAUT: Final[int] = 5

#: Sections dont le contenu ne se valide JAMAIS (cahier §7).
#:
#: L'entete est le titre du compte rendu : il reformule le geste et l'organe,
#: il n'infere rien. Mesure sur cas reels : sans cette exclusion, le titre
#: "EXAMEN ANATOMOPATHOLOGIQUE D'UNE BIOPSIE PULMONAIRE (LOBE INFERIEUR DROIT)"
#: partait en proposition et consommait une decision pour rien.
_SECTIONS_NON_VALIDABLES: Final[frozenset[str]] = frozenset({
    "entete", "titre", "identification", "technique",
})

# --- Arbitrage du college -------------------------------------------------

#: Sous-type d'une completude qui vient du completiste et non du detecteur
#: deterministe. Le depouillement peut alors comparer les deux sources plutot
#: que de les confondre dans un seul chiffre.
SOUS_TYPE_COLLEGE: Final = "college"

#: Sous-type de repli quand une soumission arbitree ne porte pas sa section.
SOUS_TYPE_RESTITUTION: Final = "restitution"

#: Motifs d'arbitrage qui passent devant tout le reste : aucun relecteur n'a
#: retrouve l'assertion dans la dictee. C'est la candidate hallucination, la
#: proposition la plus precieuse de l'etude — elle ne tombe pas hors budget.
_MOTIFS_PRIORITAIRES: Final[frozenset[str]] = frozenset(
    {MOTIF_REFUS_UNANIME, MOTIF_CITATION_INTROUVABLE}
)

_PRIORITE_HALLUCINATION: Final[int] = -1

#: Numero recopie par une lentille en tete de l'assertion qu'elle juge.
_NUMERO: Final[re.Pattern[str]] = re.compile(r"^\s*(\d{1,3})\s*[.)]\s*")


@dataclass(frozen=True)
class PropositionExtraite:
    """Une unite validable, prete a etre affichee et decidee.

    `empan_debut` / `empan_fin` sont des offsets dans le VERBATIM : c'est le
    passage de sa propre dictee que le praticien relit pour juger. Ils valent
    None quand l'assertion n'a AUCUN appui dans la dictee — voir `ancree`.
    """

    type_proposition: str
    sous_type: str
    valeur_proposee: str
    empan_debut: int | None
    empan_fin: int | None
    empan_extrait: str
    longueur_mots: int
    confiance: float | None = None
    chemin: str | None = None
    #: Faux quand rien dans la dictee ne soutient l'assertion. Ces propositions
    #: sont les CANDIDATES HALLUCINATIONS : ce sont les plus precieuses de
    #: l'etude, et l'interface doit le dire au praticien au lieu de faire comme
    #: si l'empan avait ete perdu.
    ancree: bool = True


def _nettoyer(ligne: str) -> str:
    """Retire le marquage markdown et les puces, garde le texte."""
    sans_puce = _PUCE.sub("", ligne)
    return _MARQUAGE.sub("", sans_puce).strip()


def _est_entete_seul(ligne: str) -> str | None:
    """Retourne le nom de section si la ligne n'est qu'un en-tete."""
    nu = _MARQUAGE.sub("", ligne).strip()
    if not nu or len(nu.split()) > 5:
        return None
    correspondance = _ENTETE.match(nu)
    if correspondance is None:
        return None
    return correspondance.group(1).strip().lower()


def _decouper_assertions(cr: str) -> list[tuple[str, str]]:
    """Decoupe le compte rendu en couples (section, assertion).

    Le decoupage suit la mise en forme du CR : un en-tete ouvre une section,
    une puce ou une phrase ferme une assertion. Il n'y a pas de modele ici :
    une segmentation probabiliste rendrait les empans non reproductibles.
    """
    assertions: list[tuple[str, str]] = []
    section = "entete"

    for ligne in cr.splitlines():
        if not ligne.strip():
            continue

        nom = _est_entete_seul(ligne)
        if nom is not None:
            section = nom
            continue

        inline = _ENTETE_INLINE.match(ligne)
        if inline is not None:
            section = inline.group(1).strip().lower()
            corps = inline.group(2)
        else:
            corps = ligne

        texte = _nettoyer(corps)
        if texte:
            assertions.extend(
                (section, phrase) for phrase in _phrases(texte)
            )

    return assertions


def _phrases(texte: str) -> list[str]:
    """Coupe un bloc en phrases, en gardant les abreviations intactes."""
    return [p.strip(" .;:-") for p in _FIN_PHRASE.split(texte) if p.strip(" .;:-")]


def _longueur_mots(texte: str) -> int:
    return len(texte.split())


def _assertion_jugeable(texte: str) -> bool:
    """L'assertion porte-t-elle un contenu clinique qu'on peut juger ?"""
    if _A_COMPLETER.search(texte) or _META.search(texte):
        # Un champ a completer n'est pas une affirmation du moteur : c'est un
        # aveu d'absence. Le juger comme une restitution serait un contresens.
        return False
    if _ETIQUETTE.match(texte):
        return False
    return _longueur_mots(texte) >= MIN_MOTS_ASSERTION


def _proposition(
    type_proposition: str,
    sous_type: str,
    valeur: str,
    empan: Empan | None,
    confiance: float | None = None,
    chemin: str | None = None,
) -> PropositionExtraite:
    return PropositionExtraite(
        type_proposition=type_proposition,
        sous_type=sous_type,
        valeur_proposee=valeur,
        empan_debut=empan.debut if empan else None,
        empan_fin=empan.fin if empan else None,
        empan_extrait=empan.extrait if empan else "",
        longueur_mots=_longueur_mots(valeur),
        confiance=confiance,
        chemin=chemin,
        ancree=empan is not None,
    )


def _assertions_validables(cr: str, verbatim: str) -> Iterator[tuple[str, str]]:
    """Les couples (section, assertion) que le praticien peut avoir a trancher.

    UNE seule definition de l'unite d'analyse, pour les deux voies : ce que le
    college juge et ce que le repli propose doivent etre exactement les memes
    unites, sinon les deux mesures cessent d'etre comparables et le taux de
    soumission ne veut plus rien dire.
    """
    for section, assertion in _decouper_assertions(cr):
        if section in _SECTIONS_NON_VALIDABLES:
            continue
        if not _assertion_jugeable(assertion):
            continue
        if est_copie_litterale(assertion, verbatim):
            continue
        yield section, assertion


def extraire_restitutions(cr: str, verbatim: str) -> list[PropositionExtraite]:
    """Les assertions du compte rendu qui relevent d'une inference.

    Une phrase recopiee de la dictee est ecartee : seule l'inference se valide.
    """
    retenues: list[tuple[int, PropositionExtraite]] = []

    for section, assertion in _assertions_validables(cr, verbatim):
        empan = ancrer(assertion, verbatim)
        priorite = _PRIORITE_SECTION.get(section, _PRIORITE_DEFAUT)
        if empan is None:
            # Candidate hallucination : c'est la proposition la plus precieuse
            # de l'etude, elle passe donc devant, pas a la trappe.
            priorite = _PRIORITE_HALLUCINATION
        retenues.append(
            (priorite, _proposition(TYPE_RESTITUTION, section, assertion, empan))
        )

    retenues.sort(key=lambda couple: couple[0])
    return [proposition for _, proposition in retenues]


# --- La liste numerotee soumise au college --------------------------------


@dataclass(frozen=True)
class AssertionNumerotee:
    """Une assertion du compte rendu, telle qu'elle est soumise au college."""

    rang: int
    section: str
    texte: str


def assertions_a_juger(cr: str, verbatim: str) -> list[AssertionNumerotee]:
    """Les assertions que le college doit juger, numerotees par le serveur.

    Le decoupage vient d'ICI et pas des lentilles : trois relecteurs qui
    decouperaient chacun le compte rendu ne jugeraient pas les memes unites, et
    compter leurs voix n'aurait plus de sens. Ils recoivent donc une seule liste
    numerotee.

    Les filtres sont ceux des propositions : ce qui ne se valide pas ne se relit
    pas non plus. Faire juger un en-tete ou une copie litterale de la dictee
    couterait trois appels de modele pour une unite que personne n'aurait a
    trancher.
    """
    numerotees: list[AssertionNumerotee] = []

    for section, assertion in _assertions_validables(cr, verbatim):
        numerotees.append(
            AssertionNumerotee(
                rang=len(numerotees) + 1, section=section, texte=assertion
            )
        )

    return numerotees


def rattacher_les_rangs(
    rapport: RapportCollege, assertions: list[AssertionNumerotee]
) -> RapportCollege:
    """Rattache chaque avis a l'assertion numerotee qu'il juge.

    Le rang n'est pas demande au modele, il est retrouve ici : par le numero
    recopie, sinon par le texte de l'assertion. Un avis qu'on ne sait pas
    rattacher est ECARTE plutot que devine. Le placer au hasard ferait compter
    une voix sur la mauvaise assertion, ce qui est pire qu'une voix perdue :
    l'arbitrage soumet par prudence quand il lui manque des voix, alors qu'une
    voix mal placee peut faire affirmer a tort.
    """
    par_texte = {_cle(une.texte): une.rang for une in assertions}
    rangs = {une.rang for une in assertions}

    rattaches: list[Avis] = []
    for un_avis in rapport.avis:
        rang = _rang_de(un_avis.assertion, par_texte, rangs)
        if rang is not None:
            rattaches.append(replace(un_avis, rang=rang))

    return RapportCollege(
        avis=rattaches,
        manques=list(rapport.manques),
        lentilles_muettes=list(rapport.lentilles_muettes),
    )


def _rang_de(
    assertion: str, par_texte: dict[str, int], rangs: set[int]
) -> int | None:
    """Numero de l'assertion jugee, ou None si on ne sait pas la reconnaitre."""
    numero = _NUMERO.match(assertion)
    if numero is not None and int(numero.group(1)) in rangs:
        return int(numero.group(1))
    return par_texte.get(_cle(_NUMERO.sub("", assertion)))


def _cle(texte: str) -> str:
    """Forme normalisee d'un texte, pour rapprocher deux ecritures du meme.

    Un modele recopie a la ponctuation et a la casse pres ; exiger l'octet exact
    ferait perdre des avis honnetes, donc des voix, donc de la prudence inutile.
    """
    return " ".join(jeton.forme for jeton in decouper(texte))


# --- Les propositions que le college a decide de soumettre ----------------


def extraire_restitutions_arbitrees(
    soumissions: list[dict[str, object]], verbatim: str
) -> list[PropositionExtraite]:
    """Les assertions soumises par l'arbitrage, et elles seules.

    Ce que le college a affirme a l'unanimite, citations verifiees, ne devient
    PAS une proposition : le silence est ici un bon comportement. Faire
    reconfirmer au praticien ce que trois relecteurs ont deja verifie lui coute
    un geste et dilue son attention sur ce qui compte.
    """
    retenues: list[tuple[int, PropositionExtraite]] = []

    for soumission in soumissions:
        if str(soumission.get("comportement") or "") != PROPOSER:
            continue
        assertion = str(soumission.get("assertion") or "").strip()
        if not assertion:
            continue
        section = str(soumission.get("section") or "") or SOUS_TYPE_RESTITUTION
        retenues.append((
            _priorite_arbitree(soumission, section),
            _proposition(
                TYPE_RESTITUTION,
                section,
                assertion,
                _empan_verifie(soumission, verbatim),
            ),
        ))

    # Tri stable : a priorite egale, l'ordre du compte rendu est conserve.
    retenues.sort(key=lambda couple: couple[0])
    return [proposition for _, proposition in retenues]


def _priorite_arbitree(soumission: dict[str, object], section: str) -> int:
    """Rang d'affichage d'une soumission : le motif d'abord, la section ensuite."""
    if str(soumission.get("motif") or "") in _MOTIFS_PRIORITAIRES:
        return _PRIORITE_HALLUCINATION
    return _PRIORITE_SECTION.get(section, _PRIORITE_DEFAUT)


def _empan_verifie(soumission: dict[str, object], verbatim: str) -> Empan | None:
    """L'empan qu'un relecteur a REELLEMENT retrouve dans la dictee.

    On ne remplace pas un empan manquant par un ancrage approximatif : quand
    aucun relecteur n'a retrouve le passage, cette absence EST le resultat, et
    la question posee au praticien devient "l'avez-vous dit ?". Afficher un
    surlignage la ou le college n'a rien trouve donnerait a la proposition une
    caution que personne n'a accordee.

    L'extrait est RECOUPE dans le verbatim que le serveur detient, jamais repris
    du rapport : les offsets et le texte surligne ne peuvent alors pas diverger,
    et un empan decale ferait valider un mot pour un autre.
    """
    debut = soumission.get("empan_debut")
    fin = soumission.get("empan_fin")
    if not isinstance(debut, int) or not isinstance(fin, int):
        return None
    if not 0 <= debut < fin <= len(verbatim):
        return None
    return Empan(
        debut=debut, fin=fin, extrait=verbatim[debut:fin], recouvrement=1.0
    )


def extraire_codes(
    codes: list[dict[str, object]], verbatim: str
) -> list[PropositionExtraite]:
    """Un code ADICAP par proposition, ancre sur le terme qui l'a declenche.

    Chaque code se valide separement : un code juste et un code faux dans le
    meme prelevement doivent produire deux mesures, pas une moyenne.
    """
    propositions: list[PropositionExtraite] = []

    for entree in codes:
        libelle = str(entree.get("libelle") or "")
        code = str(entree.get("code") or "")
        if not code:
            continue
        declencheur = str(entree.get("declencheur") or libelle)
        empan = ancrer(declencheur, verbatim)
        if empan is None:
            continue
        confiance = entree.get("confiance")
        propositions.append(
            _proposition(
                TYPE_CODE,
                str(entree.get("position") or "adicap"),
                code,
                empan,
                confiance=float(confiance) if isinstance(confiance, (int, float)) else None,
                chemin=libelle or None,
            )
        )

    return propositions


def extraire_completudes(
    alertes: list[dict[str, object]],
    verbatim: str,
    manques: list[dict[str, object]] | None = None,
) -> list[PropositionExtraite]:
    """Les champs signales manquants, ancres sur ce qui les rend attendus.

    Une suggestion de completude non ancree reste affichable : elle ne porte
    aucune affirmation sur la dictee, elle constate une ABSENCE. On lui donne
    alors un empan vide plutot que de la supprimer.

    Deux sources se rejoignent ici : le detecteur deterministe et le completiste
    du college. Un champ signale par les deux ne fait qu'une proposition — le
    faire trancher deux fois couterait une decision et gonflerait le
    denominateur avec le meme jugement compte deux fois.
    """
    propositions: list[PropositionExtraite] = []
    champs_vus: set[str] = set()

    for alerte in alertes:
        champ = str(alerte.get("champ") or "")
        if not champ:
            continue
        champs_vus.add(_cle(champ))
        description = str(alerte.get("description") or champ)
        empan = ancrer(description, verbatim)
        propositions.append(
            _proposition(
                TYPE_COMPLETUDE,
                str(alerte.get("section") or "completude"),
                description,
                empan,
                chemin=champ,
            )
        )

    for manque in manques or []:
        champ = str(manque.get("champ") or "")
        if not champ or _cle(champ) in champs_vus:
            continue
        champs_vus.add(_cle(champ))
        justification = str(manque.get("justification") or "") or champ
        propositions.append(
            _proposition(
                TYPE_COMPLETUDE,
                SOUS_TYPE_COLLEGE,
                justification,
                ancrer(justification, verbatim),
                chemin=champ,
            )
        )

    return propositions


def extraire(
    cr: str,
    verbatim: str,
    codes: list[dict[str, object]] | None = None,
    alertes: list[dict[str, object]] | None = None,
    budget: int = BUDGET_MAX,
    college: dict[str, object] | None = None,
) -> list[PropositionExtraite]:
    """Assemble les propositions d'un dossier, dans la limite du budget.

    Les codes et les completudes passent avant les restitutions : ils sont peu
    nombreux, ce sont les mesures les plus dures de l'etude, et les perdre au
    profit d'une dixieme phrase de microscopie appauvrirait le depouillement.

    `college` est le rapport d'arbitrage produit a la generation (trace du
    moteur). Quand il est la, ce sont ses soumissions qui font les restitutions ;
    sinon on retombe sur le decoupage.
    """
    propositions: list[PropositionExtraite] = []
    propositions.extend(extraire_codes(codes or [], verbatim))
    propositions.extend(
        extraire_completudes(
            alertes or [], verbatim, _entrees_du_college(college, "manques")
        )
    )

    place_restante = max(0, budget - len(propositions))
    propositions.extend(_restitutions(cr, verbatim, college)[:place_restante])

    return propositions[:budget]


def _restitutions(
    cr: str, verbatim: str, college: dict[str, object] | None
) -> list[PropositionExtraite]:
    """Les restitutions arbitrees si le college a siege, sinon celles du decoupage.

    La voie de repli n'est pas une politesse : une panne de relecteur ne doit pas
    arreter l'etude, et un praticien qui attend son compte rendu ne doit pas
    payer l'indisponibilite d'un fournisseur.
    """
    soumissions = _entrees_du_college(college, "soumissions")
    if not soumissions:
        return extraire_restitutions(cr, verbatim)
    return extraire_restitutions_arbitrees(soumissions, verbatim)


def _entrees_du_college(
    college: dict[str, object] | None, cle: str
) -> list[dict[str, object]]:
    """Une liste du rapport de college, ou rien s'il n'a pas siege."""
    if not isinstance(college, dict):
        return []
    entrees = college.get(cle)
    if not isinstance(entrees, list):
        return []
    return [entree for entree in entrees if isinstance(entree, dict)]


def sous_extraction(propositions: list[PropositionExtraite]) -> bool:
    """Le dossier produit-il trop peu de propositions pour etre exploitable ?

    Ce n'est pas une erreur : c'est un signal a remonter a l'administration,
    car un CR qui ne produit rien a valider n'apporte rien a l'etude.
    """
    return len(propositions) < BUDGET_CIBLE_MIN
