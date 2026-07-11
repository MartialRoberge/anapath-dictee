"""Interface commune a tous les fournisseurs LLM.

Un fournisseur recoit un ``LLMRequest`` (prompt systeme + messages + parametres)
et renvoie un ``LLMResponse`` (texte + metadonnees). Toute la logique metier
(prompts, templates, guardrails) est construite au-dessus de cette interface.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Protocol, runtime_checkable


# ---------------------------------------------------------------------------
# Exceptions — normalisees, independantes du SDK sous-jacent
# ---------------------------------------------------------------------------


class LLMError(Exception):
    """Erreur generique cote fournisseur LLM (non recuperable)."""


class LLMTransientError(LLMError):
    """Erreur temporaire (5xx, surcharge, coupure reseau) — retry possible."""


class LLMTimeoutError(LLMTransientError):
    """Depassement du delai d'attente du fournisseur."""


# ---------------------------------------------------------------------------
# Types d'echange
# ---------------------------------------------------------------------------

Role = Literal["user", "assistant"]


@dataclass(frozen=True, slots=True)
class LLMMessage:
    """Un message de la conversation adresse au modele."""

    role: Role
    content: str


@dataclass(frozen=True, slots=True)
class LLMRequest:
    """Requete normalisee envoyee a un fournisseur LLM.

    ``system`` est le prompt systeme (instructions + template rendu).
    ``json_object`` force une sortie JSON quand le fournisseur le supporte.
    """

    system: str
    messages: list[LLMMessage]
    temperature: float = 0.0
    max_tokens: int = 8192
    json_object: bool = True


@dataclass(frozen=True, slots=True)
class LLMResponse:
    """Reponse normalisee d'un fournisseur LLM."""

    text: str
    model: str
    provider: str
    truncated: bool = False
    usage: dict[str, int] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Protocole fournisseur
# ---------------------------------------------------------------------------


@runtime_checkable
class LLMProvider(Protocol):
    """Contrat minimal d'un fournisseur de generation de texte."""

    name: str
    model: str

    async def complete(self, request: LLMRequest) -> LLMResponse:
        """Genere une reponse pour la requete donnee.

        Doit lever ``LLMTimeoutError`` / ``LLMTransientError`` pour les erreurs
        recuperables et ``LLMError`` pour les erreurs definitives. Le decorateur
        de retry (``reports/`` ou appelant) s'appuie sur cette distinction.
        """
        ...

    async def aclose(self) -> None:
        """Libere les ressources reseau (clients HTTP)."""
        ...
