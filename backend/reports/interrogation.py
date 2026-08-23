"""Un aller-retour avec une lentille, et rien d'autre.

Les deux colleges — amont sur la dictee, aval sur le compte rendu — posent des
questions differentes mais de la meme facon : un prompt systeme, un contenu, une
reponse JSON, et le droit de ne pas repondre. Cette mecanique vit ici pour ne
pas etre ecrite deux fois.

DEUX CHOIX QUI VALENT POUR TOUTES LES LENTILLES

Temperature nulle : on veut un jugement reproductible, pas de la creativite. Un
verdict qui change d'une execution a l'autre ne se publie pas.

Une lentille muette ne fait jamais echouer la generation. Le compte rendu existe
sans elle ; le college ne fait que l'eclairer. Un praticien ne doit pas se
retrouver bloque parce qu'un relecteur n'a pas repondu.
"""

from __future__ import annotations

import logging
from typing import Final

from llm.base import LLMMessage, LLMProvider, LLMRequest
from reports.guardrails import parse_llm_json

logger = logging.getLogger("anapath.college")

TEMPERATURE: Final[float] = 0.0
MAX_TOKENS: Final[int] = 4096


async def interroger(
    provider: LLMProvider, systeme: str, contenu: str
) -> dict[str, object] | None:
    """Interroge une lentille. Retourne None si elle n'a pas repondu.

    Toute erreur est ravalee volontairement : reseau, quota, JSON illisible. Du
    point de vue de l'appelant il n'y a qu'un cas, la lentille s'est tue, et il
    n'a qu'un comportement a prevoir.
    """
    requete = LLMRequest(
        system=systeme,
        messages=[LLMMessage(role="user", content=contenu)],
        temperature=TEMPERATURE,
        max_tokens=MAX_TOKENS,
    )
    try:
        reponse = await provider.complete(requete)
        charge = parse_llm_json(reponse.text)
    except Exception as erreur:  # noqa: BLE001
        logger.warning("Lentille muette : %s", erreur)
        return None
    return charge if isinstance(charge, dict) else None
