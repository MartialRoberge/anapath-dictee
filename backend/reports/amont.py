"""Le college AMONT : lever le doute AVANT de rediger.

POURQUOI EN AMONT ET PAS SEULEMENT EN AVAL

Critiquer apres coup, c'est laisser l'erreur s'ecrire puis demander au praticien
de la rattraper. Chaque doute leve AVANT la redaction produit un compte rendu
juste du premier coup — et supprime la proposition qu'il aurait fallu lui faire
valider ensuite. Le bon indicateur d'un doute leve en amont n'est donc pas
"combien de questions ai-je posees" mais "combien de verifications ai-je
epargnees".

Les deux colleges ne font pas le meme travail :

    AMONT   sur la DICTEE      -> qu'a-t-il dit, au juste ? que faut-il demander ?
    AVAL    sur le COMPTE RENDU -> ce qui a ete ecrit tient-il ?

CE QUI NE CHANGE PAS, ET QUI EST LE PLUS IMPORTANT

La redaction reste UNE SEULE PASSE PROPRE. Aucun agent ne co-redige, aucun
comite ne repasse sur le texte. Les agents amont ne font qu'INFORMER la
redaction — lecture consolidee, reponses du praticien, sources applicables — et
les agents aval ne font que l'ANNOTER. Un compte rendu ecrit par un comite
serait plat, redondant et plus faux, pas moins : c'est exactement la qualite du
modele en direct qu'il ne faut pas perdre.

MESURABLE PLUTOT QUE CROYABLE

Les deux colleges se coupent separement par configuration. On peut donc mesurer
quatre regimes sur le meme corpus — nu, amont seul, aval seul, les deux — au
lieu d'affirmer que la complexite ajoutee est utile.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Final

from llm.base import LLMProvider
from reports.interrogation import interroger

logger = logging.getLogger("anapath.amont")

#: Budget de questions par compte rendu (Politique_de_questions §5). Trois
#: questions, c'est un assistant ; douze, c'est un formulaire — et le formulaire
#: est exactement ce qui fait abandonner les outils de dictee.
BUDGET_QUESTIONS: Final[int] = 3


@dataclass(frozen=True)
class Lecture:
    """Un element que le praticien a dicte, avec ce qu'il en a dit exactement.

    `citation` est la matiere premiere de l'explicabilite : c'est elle qui
    permettra plus tard d'afficher, sous un bloc du compte rendu, le passage de
    la dictee dont il sort. Une lecture sans citation n'est pas exploitable.
    """

    champ: str
    valeur: str
    citation: str


@dataclass(frozen=True)
class Contestation:
    """Une lecture que le contradicteur juge discutable.

    `alternative` est ce que le contradicteur aurait lu a la place. C'est ce qui
    transforme un desaccord en question fermee : sans autre option a proposer,
    il n'y a rien a demander au praticien.
    """

    champ: str
    lecture_contestee: str
    alternative: str
    motif: str


@dataclass(frozen=True)
class Doute:
    """Une ambiguite qui CHANGE la sortie, et la question qui la leve.

    La regle de valeur d'information s'applique ici : si toutes les reponses
    aboutissent au meme compte rendu et aux memes codes, la question ne se pose
    pas, meme si le systeme est incertain.
    """

    champ: str
    question: str
    options: tuple[str, ...]
    citation: str
    #: Ce que la reponse determine. Un doute sans impact declare est ecarte :
    #: c'est la seule facon d'empecher le compteur de questions d'exploser.
    impact: str


@dataclass
class RapportAmont:
    """Ce que le college amont a compris, et ce dont il doute."""

    lectures: list[Lecture] = field(default_factory=list)
    contestations: list[Contestation] = field(default_factory=list)
    doutes: list[Doute] = field(default_factory=list)
    lentilles_muettes: list[str] = field(default_factory=list)

    @property
    def champs_certains(self) -> set[str]:
        """Champs lus sans contestation : la redaction peut s'y appuyer."""
        contestes = {c.champ for c in self.contestations}
        return {lecture.champ for lecture in self.lectures} - contestes


# --- Les trois lentilles ---------------------------------------------------

#: Le lecteur ne conclut pas, il releve. On lui interdit d'inferer parce que
#: c'est cette lecture qui servira de source a tout l'aval : une inference
#: glissee ici serait ensuite citee comme si le praticien l'avait dite.
_LECTEUR: Final[str] = (
    "Tu releves ce que le praticien a DIT, rien de plus. Tu n'es pas la pour "
    "conclure, ni pour completer, ni pour corriger.\n"
    "Pour chaque element : le champ, la valeur telle qu'elle a ete dictee, et la "
    "CITATION EXACTE de la dictee, recopiee mot pour mot sans la corriger.\n"
    "N'invente aucun champ. Si le praticien n'a pas dit la lateralite, ne mets "
    "pas de lateralite : une absence est une information juste.\n"
    "Champs usuels : geste, organe, lateralite, nombre de prelevements, "
    "dimensions, nombre de blocs, ganglions, constatations microscopiques, "
    "immunohistochimie, conclusion dictee.\n\n"
    "Reponds UNIQUEMENT par un objet JSON :\n"
    '{"lectures": [{"champ": "...", "valeur": "...", "citation": "..."}]}'
)

#: Le contradicteur ne cherche pas a avoir raison : il cherche a montrer qu'une
#: autre lecture tient. Sans lui, la premiere lecture devient la verite par
#: defaut, et une erreur de lecture se propage jusqu'au compte rendu final.
_CONTRADICTEUR: Final[str] = (
    "On te donne une dictee et la lecture qu'un premier agent en a faite. Ton "
    "role est de la CONTESTER quand une autre lecture tient aussi bien.\n"
    "Ne conteste que si tu peux proposer une ALTERNATIVE precise : un desaccord "
    "sans autre option a proposer ne sert a rien.\n"
    "Cherche en particulier : un geste lu plus precisement que la dictee ne le "
    "permet (lobe entendu comme lobectomie) ; une lateralite deduite plutot que "
    "dictee ; un nombre reconstruit ; une constatation transformee en diagnostic ; "
    "un terme que la transcription a pu deformer.\n"
    "Si la lecture est fidele, ne conteste pas. Une liste vide est une bonne "
    "reponse et c'est la reponse la plus frequente.\n\n"
    "Reponds UNIQUEMENT par un objet JSON :\n"
    '{"contestations": [{"champ": "...", "lecture_contestee": "...", '
    '"alternative": "...", "motif": "..."}]}'
)

#: Le leve-doute est le plus contraint des trois, parce qu'il est le seul dont
#: la sortie coute quelque chose au praticien : une question.
_LEVE_DOUTE: Final[str] = (
    "Tu identifies ce qui est ambigu dans la dictee ET QUI CHANGE LA SORTIE.\n\n"
    "LA REGLE, applique-la litteralement : ne signale un doute que si les "
    "reponses possibles conduisent a des comptes rendus DIFFERENTS. Si deux "
    "lectures aboutissent au meme texte et aux memes codes, il n'y a pas de "
    "doute a lever, meme si tu es incertain. L'incertitude ne suffit pas ; seule "
    "l'incertitude qui change quelque chose compte.\n\n"
    "Deuxieme filtre : on ne demande que ce qui est DANS LA TETE DU PRATICIEN et "
    "coute un tap. Il sait s'il a recu une thyroide entiere ou un lobe, il ne "
    "l'a simplement pas dit — on demande. Il ne sait pas ce qu'il n'a pas "
    "observe — on s'abstient, sans question.\n\n"
    "Trois questions au maximum, et moins est mieux. Chaque question doit citer "
    "le passage de la dictee qui la declenche : une question sans declencheur "
    "affichable ne se pose pas.\n"
    "Deux ou trois options fermees, jamais de texte libre, et toujours une issue "
    "de type je ne sais pas.\n\n"
    "Reponds UNIQUEMENT par un objet JSON :\n"
    '{"doutes": [{"champ": "...", "question": "...", "options": ["...", "..."], '
    '"citation": "...", "impact": "..."}]}\n'
    "Liste vide si rien ne merite d'etre demande. C'est le cas le plus frequent."
)


def _message_lecteur(transcription: str) -> str:
    return f"DICTEE DU PRATICIEN :\n{transcription}"


def _message_avec_lecture(transcription: str, lectures: list[Lecture]) -> str:
    """La dictee plus la lecture a contester ou a interroger."""
    lignes = "\n".join(
        f"- {lecture.champ} = {lecture.valeur}   (cite : {lecture.citation})"
        for lecture in lectures
    )
    return (
        f"DICTEE DU PRATICIEN :\n{transcription}\n\n"
        f"LECTURE FAITE PAR UN PREMIER AGENT :\n{lignes or '(aucune lecture)'}"
    )


def _lire_lectures(charge: dict[str, object]) -> list[Lecture]:
    brut = charge.get("lectures")
    if not isinstance(brut, list):
        return []
    lectures: list[Lecture] = []
    for entree in brut:
        if not isinstance(entree, dict):
            continue
        champ = str(entree.get("champ") or "").strip()
        valeur = str(entree.get("valeur") or "").strip()
        if champ and valeur:
            lectures.append(
                Lecture(
                    champ=champ,
                    valeur=valeur,
                    citation=str(entree.get("citation") or "").strip(),
                )
            )
    return lectures


def _lire_contestations(charge: dict[str, object]) -> list[Contestation]:
    brut = charge.get("contestations")
    if not isinstance(brut, list):
        return []
    contestations: list[Contestation] = []
    for entree in brut:
        if not isinstance(entree, dict):
            continue
        champ = str(entree.get("champ") or "").strip()
        alternative = str(entree.get("alternative") or "").strip()
        # Une contestation sans alternative n'ouvre sur rien : on l'ecarte
        # plutot que d'installer un doute qu'on ne saurait pas lever.
        if champ and alternative:
            contestations.append(
                Contestation(
                    champ=champ,
                    lecture_contestee=str(entree.get("lecture_contestee") or "").strip(),
                    alternative=alternative,
                    motif=str(entree.get("motif") or "").strip(),
                )
            )
    return contestations


def _lire_doutes(charge: dict[str, object]) -> list[Doute]:
    brut = charge.get("doutes")
    if not isinstance(brut, list):
        return []
    doutes: list[Doute] = []
    for entree in brut:
        if not isinstance(entree, dict):
            continue
        question = str(entree.get("question") or "").strip()
        options = entree.get("options")
        citation = str(entree.get("citation") or "").strip()
        impact = str(entree.get("impact") or "").strip()
        # Trois exigences, et chacune retire des questions inutiles : une
        # question sans options fermees devient du texte libre ; sans citation
        # elle n'a pas de declencheur affichable ; sans impact declare, rien ne
        # prouve que la reponse change quoi que ce soit.
        if not (question and isinstance(options, list) and citation and impact):
            continue
        fermees = tuple(str(o).strip() for o in options if str(o).strip())
        if len(fermees) < 2:
            continue
        doutes.append(
            Doute(
                champ=str(entree.get("champ") or "").strip(),
                question=question,
                options=fermees,
                citation=citation,
                impact=impact,
            )
        )
    return doutes


async def reunir_le_college_amont(
    provider: LLMProvider, transcription: str
) -> RapportAmont:
    """Lit la dictee, la conteste, et en tire les questions qui valent la peine.

    Deux temps, pas trois : le contradicteur et le leve-doute ont tous deux
    besoin de la lecture, donc ils partent ensemble APRES elle. Ils ne se voient
    pas l'un l'autre — un contradicteur qui verrait les questions s'alignerait
    dessus, et son desaccord ne voudrait plus rien dire.
    """
    rapport = RapportAmont()

    charge = await interroger(provider, _LECTEUR, _message_lecteur(transcription))
    if charge is None:
        # Sans lecture, il n'y a rien a contester ni a interroger. La redaction
        # se fera sans le college amont, ce qui est le comportement nu.
        rapport.lentilles_muettes.extend(["lecteur", "contradicteur", "leve_doute"])
        return rapport
    rapport.lectures.extend(_lire_lectures(charge))

    contenu = _message_avec_lecture(transcription, rapport.lectures)
    contestation, doute = await asyncio.gather(
        interroger(provider, _CONTRADICTEUR, contenu),
        interroger(provider, _LEVE_DOUTE, contenu),
    )

    if contestation is None:
        rapport.lentilles_muettes.append("contradicteur")
    else:
        rapport.contestations.extend(_lire_contestations(contestation))

    if doute is None:
        rapport.lentilles_muettes.append("leve_doute")
    else:
        rapport.doutes.extend(_lire_doutes(doute))

    return rapport


def questions_a_poser(rapport: RapportAmont) -> list[Doute]:
    """Les questions retenues, dans la limite du budget.

    On garde d'abord celles qui portent sur un champ CONTESTE : le contradicteur
    et le leve-doute se sont accordes pour dire que quelque chose cloche au meme
    endroit, ce qui est le signal le plus fort dont on dispose en amont.
    """
    contestes = {c.champ for c in rapport.contestations}
    prioritaires = [d for d in rapport.doutes if d.champ in contestes]
    autres = [d for d in rapport.doutes if d.champ not in contestes]
    return (prioritaires + autres)[:BUDGET_QUESTIONS]
