"""Le college de relecture : plusieurs avis independants sur un meme compte rendu.

POURQUOI PLUSIEURS AGENTS PLUTOT QU'UN SEUL

Un modele seul qui s'auto-evalue est complaisant : il a produit le texte, il le
trouve bon. Trois relecteurs a qui l'on donne des LENTILLES DIFFERENTES, et qui
ne savent pas qu'un confrere les relit, se contredisent la ou le texte est
fragile. Ce desaccord est le signal : il localise l'incertitude reelle, celle
qui merite l'attention du praticien.

DEUX REGLES QUI EMPECHENT LE COLLEGE D'AJOUTER DES HALLUCINATIONS

1. UN RELECTEUR NE REECRIT JAMAIS. Il ne produit pas de texte medical, il rend
   un verdict et cite un passage. Sa sortie est un vote, pas de la prose. Un
   agent qui ne redige pas ne peut pas inventer de contenu clinique.
2. TOUTE CITATION EST VERIFIEE CONTRE LA DICTEE, cote serveur, par recherche
   exacte. Un relecteur qui cite un passage inexistant voit son verdict bascule
   en NON SOUTENU, quoi qu'il ait repondu. C'est le verrou : le college ne peut
   pas fabriquer une preuve, il ne peut que la designer.

L'ARBITRAGE EST DETERMINISTE (voir etude/arbitrage.py). Aucun quatrieme modele
ne tranche : ce sont des comptes de voix. L'explication affichee au praticien
n'est donc pas GENEREE, elle est CONSTATEE — c'est ce qui la rend defendable.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Final

from llm.base import LLMMessage, LLMProvider, LLMRequest
from reports.guardrails import GenerationParseError, parse_llm_json

logger = logging.getLogger("anapath.college")

#: Temperature nulle : on veut un jugement reproductible, pas de la creativite.
#: Un verdict qui change d'une execution a l'autre ne se publie pas.
_TEMPERATURE: Final[float] = 0.0

_MAX_TOKENS: Final[int] = 4096


@dataclass(frozen=True)
class Lentille:
    """Un point de vue de relecture.

    Chaque lentille cherche UNE chose. Trois relecteurs identiques ne
    produiraient qu'un vote triple ; ce sont les angles differents qui font que
    le desaccord veut dire quelque chose.
    """

    cle: str
    intitule: str
    consigne: str


#: Le litteraliste. Il ne connait pas la medecine, il compare des mots. C'est
#: exactement ce qu'on veut pour detecter le non-dicte : un relecteur savant
#: comblerait les trous avec ce qu'il sait, et validerait une invention
#: plausible.
_LITTERALISTE: Final = Lentille(
    cle="litteraliste",
    intitule="Fidélité littérale",
    consigne=(
        "Tu compares deux textes, rien d'autre. Tu n'es PAS medecin et tu ne "
        "dois RIEN completer avec des connaissances medicales : un fait vrai en "
        "general mais absent de la dictee est, ici, non soutenu.\n"
        "Pour chaque assertion du compte rendu, dis si la DICTEE la soutient, et "
        "cite le passage EXACT de la dictee qui la soutient — recopie-le mot pour "
        "mot, sans le corriger ni le reformuler. Si aucun passage ne la soutient, "
        "reponds soutenue=false et laisse la citation vide.\n"
        "Une reformulation fidele reste soutenue. Une precision ajoutee ne l'est "
        "pas : 'adenocarcinome moyennement differencie' n'est pas soutenu par "
        "'adenocarcinome' seul."
    ),
)

#: Le clinicien sceptique. Il cherche le pas de trop — le grade, le stade,
#: l'envahissement affirmes plus fermement que la dictee ne le permet. C'est le
#: mode de defaillance dangereux : plausible, bien ecrit, et faux.
_SCEPTIQUE: Final = Lentille(
    cle="sceptique",
    intitule="Sur-interprétation",
    consigne=(
        "Tu es un anatomopathologiste relecteur, et tu cherches la SUR-"
        "INTERPRETATION : ce que le compte rendu affirme plus fermement que la "
        "dictee ne l'autorise.\n"
        "Signale en particulier : un grade ou un stade derive alors qu'il n'a pas "
        "ete dicte ; une atteinte ganglionnaire, un envahissement, des emboles ou "
        "des marges affirmes sans avoir ete dictes ; une certitude diagnostique "
        "posee sur une description qui ne la porte pas ; une negation transformee "
        "en affirmation ou l'inverse.\n"
        "Une inference DEFINITIONNELLE est legitime : si la dictee decrit une "
        "lesion dont le nom decoule de la definition, la nommer n'est pas une "
        "sur-interpretation. Ce qui ne l'est pas : une valeur VARIABLE d'un cas a "
        "l'autre, qui ne s'infere pas et se mesure."
    ),
)

#: Le completiste. Il regarde ce qui MANQUE. Son verdict porte donc sur une
#: absence, et il n'a pas de citation a produire.
_COMPLETISTE: Final = Lentille(
    cle="completiste",
    intitule="Complétude",
    consigne=(
        "Tu es un anatomopathologiste relecteur, et tu regardes ce qui MANQUE au "
        "compte rendu pour ce type de prelevement.\n"
        "Ne signale que ce qui est ATTENDU ET ABSENT, et dont l'absence changerait "
        "la prise en charge ou la lecture du compte rendu. Ne signale jamais un "
        "champ que la dictee ne permet pas de remplir sans le deviner : ton role "
        "est de dire ce qui manque, jamais de proposer une valeur.\n"
        "Sois avare. Trois manques reels valent mieux que dix rappels de "
        "formulaire : chaque signalement coute une verification au praticien."
    ),
)

LENTILLES: Final[tuple[Lentille, ...]] = (_LITTERALISTE, _SCEPTIQUE, _COMPLETISTE)


@dataclass(frozen=True)
class Avis:
    """Le jugement d'une lentille sur une assertion.

    `citation_verifiee` n'est PAS renseigne par le modele : il est calcule cote
    serveur (voir `etude/arbitrage.py`). Un modele qui s'auto-declarerait
    verifie annulerait le verrou.
    """

    lentille: str
    assertion: str
    soutenue: bool
    citation: str = ""
    motif: str = ""
    #: Numero de l'assertion jugee, dans la liste numerotee soumise au college.
    #: Comme `citation_verifiee`, il n'est PAS renseigne par le modele : il est
    #: rattache cote serveur (voir `etude/extraction.rattacher_les_rangs`), sinon
    #: une lentille pourrait deplacer son vote sur une autre assertion.
    rang: int = 0


@dataclass(frozen=True)
class Manque:
    """Un champ juge attendu et absent par le completiste."""

    champ: str
    justification: str


@dataclass
class RapportCollege:
    """Ce que le college a rendu, avis bruts et incidents compris."""

    avis: list[Avis] = field(default_factory=list)
    manques: list[Manque] = field(default_factory=list)
    #: Lentilles qui n'ont pas repondu. Une lentille muette abaisse le quorum :
    #: l'arbitrage doit le savoir pour ne pas lire un desaccord la ou il n'y a
    #: qu'une panne.
    lentilles_muettes: list[str] = field(default_factory=list)

    @property
    def quorum(self) -> int:
        """Nombre de lentilles qui se sont reellement exprimees."""
        return len(LENTILLES) - len(self.lentilles_muettes)


def _prompt_systeme(lentille: Lentille) -> str:
    """Consigne de la lentille, plus le format de sortie impose."""
    return (
        f"{lentille.consigne}\n\n"
        "Reponds UNIQUEMENT par un objet JSON de cette forme, sans commentaire :\n"
        '{"avis": [{"assertion": "...", "soutenue": true, '
        '"citation": "...", "motif": "..."}]}\n'
        "- assertion : recopie l'assertion du compte rendu, telle quelle.\n"
        "- citation : un extrait EXACT de la dictee, recopie sans modification. "
        "Vide si tu n'en trouves pas.\n"
        "- motif : une phrase courte, en francais.\n"
        "N'invente jamais de citation : une citation introuvable dans la dictee "
        "invalide ton avis."
    )


def _prompt_completiste() -> str:
    return (
        f"{_COMPLETISTE.consigne}\n\n"
        "Reponds UNIQUEMENT par un objet JSON de cette forme :\n"
        '{"manques": [{"champ": "...", "justification": "..."}]}\n'
        "Liste vide si rien ne manque. C'est une reponse acceptable et frequente."
    )


#: Assertions soumises en une fois a une lentille.
#:
#: Mesure sur cas reels : interrogee sur vingt-trois assertions d'un coup, une
#: lentille n'en jugeait qu'une partie et choisissait lesquelles. L'arbitrage
#: lisait alors un vote unique la ou il en attendait deux, concluait au quorum
#: insuffisant, et soumettait par prudence — 23 soumissions sur 42 pour cette
#: seule raison. Ce n'etait pas du doute, c'etait une omission.
#:
#: Huit tient dans l'attention d'un modele. Les lots partent en parallele, donc
#: le decoupage ne coute pas de latence.
LOT_ASSERTIONS: Final[int] = 8


def _message(transcription: str, cr: str, lot: list[tuple[int, str]]) -> str:
    """La dictee, le compte rendu, et le lot d'assertions a juger."""
    numerotees = "\n".join(f"{rang}. {texte}" for rang, texte in lot)
    return (
        "DICTEE DU PRATICIEN (verbatim, source de verite) :\n"
        f"{transcription}\n\n"
        "COMPTE RENDU PRODUIT PAR LE SYSTEME :\n"
        f"{cr}\n\n"
        "ASSERTIONS A JUGER — juge-les TOUTES, une par une, sans en omettre "
        "aucune et en gardant leur numero :\n"
        f"{numerotees}"
    )


def _lots(assertions: list[tuple[int, str]]) -> list[list[tuple[int, str]]]:
    """Decoupe la liste en lots que le modele juge sans en oublier."""
    return [
        assertions[debut:debut + LOT_ASSERTIONS]
        for debut in range(0, len(assertions), LOT_ASSERTIONS)
    ] or [[]]


async def _interroger(
    provider: LLMProvider, systeme: str, contenu: str
) -> dict[str, object] | None:
    """Un aller-retour avec une lentille. None si elle n'a pas repondu.

    Une lentille muette ne doit jamais faire echouer la generation : le compte
    rendu existe deja, le college ne fait que l'eclairer.
    """
    requete = LLMRequest(
        system=systeme,
        messages=[LLMMessage(role="user", content=contenu)],
        temperature=_TEMPERATURE,
        max_tokens=_MAX_TOKENS,
    )
    try:
        reponse = await provider.complete(requete)
        return parse_llm_json(reponse.text)
    except (GenerationParseError, Exception) as erreur:  # noqa: BLE001
        logger.warning("Lentille muette : %s", erreur)
        return None


def _lire_avis(lentille: Lentille, charge: dict[str, object]) -> list[Avis]:
    """Convertit la reponse d'une lentille en avis, en ignorant le mal forme."""
    brut = charge.get("avis")
    if not isinstance(brut, list):
        return []
    avis: list[Avis] = []
    for entree in brut:
        if not isinstance(entree, dict):
            continue
        assertion = str(entree.get("assertion") or "").strip()
        if not assertion:
            continue
        avis.append(
            Avis(
                lentille=lentille.cle,
                assertion=assertion,
                soutenue=bool(entree.get("soutenue")),
                citation=str(entree.get("citation") or "").strip(),
                motif=str(entree.get("motif") or "").strip(),
            )
        )
    return avis


def _lire_manques(charge: dict[str, object]) -> list[Manque]:
    brut = charge.get("manques")
    if not isinstance(brut, list):
        return []
    manques: list[Manque] = []
    for entree in brut:
        if not isinstance(entree, dict):
            continue
        champ = str(entree.get("champ") or "").strip()
        if champ:
            manques.append(
                Manque(champ=champ, justification=str(entree.get("justification") or ""))
            )
    return manques


async def reunir_le_college(
    provider: LLMProvider,
    transcription: str,
    cr: str,
    assertions: list[tuple[int, str]] | None = None,
) -> RapportCollege:
    """Interroge les lentilles en parallele et rassemble leurs avis.

    En parallele parce qu'elles doivent etre INDEPENDANTES : une lentille qui
    verrait le verdict d'une autre s'alignerait dessus, et l'accord ne
    signifierait plus rien.

    Les assertions partent par LOTS. Interrogee sur une longue liste, une
    lentille en juge une partie et choisit lesquelles ; l'arbitrage lit alors un
    vote unique la ou il en attend deux et soumet par prudence. Les lots partent
    eux aussi en parallele, donc le decoupage ne coute pas de latence.
    """
    juges = [lentille for lentille in LENTILLES if lentille is not _COMPLETISTE]
    lots = _lots(assertions or [])

    appels = [
        _interroger(provider, _prompt_systeme(lentille), _message(transcription, cr, lot))
        for lentille in juges
        for lot in lots
    ]
    appels.append(
        _interroger(provider, _prompt_completiste(), _message(transcription, cr, []))
    )
    reponses = await asyncio.gather(*appels)

    rapport = RapportCollege()
    curseur = 0
    for lentille in juges:
        charges = reponses[curseur:curseur + len(lots)]
        curseur += len(lots)
        if all(charge is None for charge in charges):
            # Muette seulement si AUCUN lot n'a repondu : un lot manquant sur
            # trois n'est pas une panne de lentille, et l'annoncer comme telle
            # abaisserait le quorum de toutes les assertions.
            rapport.lentilles_muettes.append(lentille.cle)
            continue
        for charge in charges:
            if charge is not None:
                rapport.avis.extend(_lire_avis(lentille, charge))

    charge_completiste = reponses[-1]
    if charge_completiste is None:
        rapport.lentilles_muettes.append(_COMPLETISTE.cle)
    else:
        rapport.manques.extend(_lire_manques(charge_completiste))

    return rapport
