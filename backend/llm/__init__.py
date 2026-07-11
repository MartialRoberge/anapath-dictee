"""Abstraction fournisseur LLM.

Ce package isole le reste de l'application de tout fournisseur de generation
de texte concret (Mistral, Anthropic, ...). Le moteur de compte-rendu
(``reports/``) ne depend que de l'interface ``LLMProvider`` et des types
``LLMRequest`` / ``LLMResponse`` definis ici — jamais d'un SDK precis.

Changer de moteur = changer ``LLM_PROVIDER`` dans la configuration, sans
toucher au code metier.
"""

from llm.base import (
    LLMError,
    LLMMessage,
    LLMProvider,
    LLMRequest,
    LLMResponse,
    LLMTimeoutError,
    LLMTransientError,
)
from llm.factory import get_llm_provider

__all__ = [
    "LLMError",
    "LLMMessage",
    "LLMProvider",
    "LLMRequest",
    "LLMResponse",
    "LLMTimeoutError",
    "LLMTransientError",
    "get_llm_provider",
]
