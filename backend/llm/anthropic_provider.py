"""Fournisseur LLM Anthropic (Claude) — conserve comme alternative.

N'est plus le moteur par defaut (Mistral l'est) mais reste disponible via
``LLM_PROVIDER=anthropic`` pour comparaison de qualite ou repli.
"""

from __future__ import annotations

import anthropic
from anthropic.types import TextBlock

from llm.base import (
    LLMError,
    LLMProvider,
    LLMRequest,
    LLMResponse,
    LLMTimeoutError,
    LLMTransientError,
)


class AnthropicProvider:
    """Implementation ``LLMProvider`` pour Claude."""

    name: str = "anthropic"

    def __init__(
        self,
        api_key: str,
        model: str,
        timeout_seconds: float = 120.0,
    ) -> None:
        self.model: str = model
        self._client: anthropic.AsyncAnthropic = anthropic.AsyncAnthropic(
            api_key=api_key,
            timeout=timeout_seconds,
        )

    async def complete(self, request: LLMRequest) -> LLMResponse:
        """Appelle l'API Messages d'Anthropic."""
        messages: list[dict[str, str]] = [
            {"role": msg.role, "content": msg.content} for msg in request.messages
        ]

        # Claude n'a pas de mode JSON natif : la contrainte de sortie JSON est
        # portee par le prompt systeme (voir reports/prompts.py).
        try:
            response = await self._client.messages.create(
                model=self.model,
                max_tokens=request.max_tokens,
                temperature=request.temperature,
                system=[
                    {
                        "type": "text",
                        "text": request.system,
                        "cache_control": {"type": "ephemeral"},
                    }
                ],
                messages=messages,  # type: ignore[arg-type]
            )
        except anthropic.APITimeoutError as exc:
            raise LLMTimeoutError(f"Timeout Claude : {exc}") from exc
        except anthropic.APIConnectionError as exc:
            raise LLMTransientError(f"Erreur connexion Claude : {exc}") from exc
        except anthropic.APIStatusError as exc:
            if exc.status_code in (429, 500, 502, 503, 504, 529):
                raise LLMTransientError(
                    f"Claude a repondu {exc.status_code} (temporaire)."
                ) from exc
            raise LLMError(f"Claude a repondu {exc.status_code} : {exc}") from exc

        truncated: bool = response.stop_reason == "max_tokens"

        if not response.content:
            raise LLMError("Claude n'a retourne aucun bloc.")
        first_block = response.content[0]
        if not isinstance(first_block, TextBlock):
            raise LLMError("Claude n'a pas retourne de texte.")

        usage: dict[str, int] = {
            "prompt_tokens": response.usage.input_tokens,
            "completion_tokens": response.usage.output_tokens,
        }

        return LLMResponse(
            text=first_block.text,
            model=self.model,
            provider=AnthropicProvider.name,
            truncated=truncated,
            usage=usage,
        )

    async def aclose(self) -> None:
        await self._client.close()


_: type[LLMProvider] = AnthropicProvider
