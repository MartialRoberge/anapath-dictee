"""Selection du fournisseur LLM actif depuis la configuration.

Point d'entree unique : ``get_llm_provider()``. Le reste de l'application
n'instancie jamais un fournisseur concret directement.
"""

from __future__ import annotations

from config import Settings, get_settings
from llm.base import LLMError, LLMProvider

_provider_singleton: LLMProvider | None = None


def build_llm_provider(settings: Settings) -> LLMProvider:
    """Construit un fournisseur LLM selon ``settings.llm_provider``.

    Fournisseurs supportes : ``mistral`` (defaut), ``anthropic``.
    """
    provider_name: str = settings.llm_provider.strip().lower()

    if provider_name == "mistral":
        from llm.mistral import MistralProvider

        return MistralProvider(
            api_key=settings.mistral_api_key,
            model=settings.mistral_model,
            timeout_seconds=settings.llm_timeout_seconds,
        )

    if provider_name == "anthropic":
        from llm.anthropic_provider import AnthropicProvider

        return AnthropicProvider(
            api_key=settings.anthropic_api_key,
            model=settings.claude_model,
            timeout_seconds=settings.llm_timeout_seconds,
        )

    raise LLMError(
        f"Fournisseur LLM inconnu : '{settings.llm_provider}'. "
        "Valeurs supportees : mistral, anthropic."
    )


def get_llm_provider() -> LLMProvider:
    """Retourne le fournisseur LLM actif (singleton par processus)."""
    global _provider_singleton
    if _provider_singleton is None:
        _provider_singleton = build_llm_provider(get_settings())
    return _provider_singleton


def reset_llm_provider() -> LLMProvider | None:
    """Reinitialise le singleton (tests, changement de config).

    Retourne l'ancien fournisseur pour que l'appelant puisse le fermer.
    """
    global _provider_singleton
    previous = _provider_singleton
    _provider_singleton = None
    return previous
