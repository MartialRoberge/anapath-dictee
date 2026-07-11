"""Fournisseur LLM Mistral (API souveraine) via l'API chat completions.

Utilise httpx directement plutot que le SDK ``mistralai`` : moins de
dependances, meme approche que la transcription Voxtral, et controle total
sur le mapping d'erreurs vers ``llm.base``.
"""

from __future__ import annotations

import httpx

from llm.base import (
    LLMError,
    LLMProvider,
    LLMRequest,
    LLMResponse,
    LLMTimeoutError,
    LLMTransientError,
)

MISTRAL_CHAT_URL: str = "https://api.mistral.ai/v1/chat/completions"

# Codes HTTP consideres comme temporaires (retry pertinent).
_TRANSIENT_STATUS: frozenset[int] = frozenset({408, 409, 425, 429, 500, 502, 503, 504})


class MistralProvider:
    """Implementation ``LLMProvider`` pour Mistral."""

    name: str = "mistral"

    def __init__(
        self,
        api_key: str,
        model: str,
        timeout_seconds: float = 120.0,
    ) -> None:
        self.model: str = model
        self._api_key: str = api_key
        self._client: httpx.AsyncClient = httpx.AsyncClient(
            timeout=timeout_seconds,
            base_url="https://api.mistral.ai",
        )

    async def complete(self, request: LLMRequest) -> LLMResponse:
        """Appelle l'endpoint chat completions de Mistral."""
        if not self._api_key:
            raise LLMError("MISTRAL_API_KEY absente : moteur Mistral non configure.")

        messages: list[dict[str, str]] = [
            {"role": "system", "content": request.system}
        ]
        for msg in request.messages:
            messages.append({"role": msg.role, "content": msg.content})

        payload: dict[str, object] = {
            "model": self.model,
            "messages": messages,
            "temperature": request.temperature,
            "max_tokens": request.max_tokens,
        }
        if request.json_object:
            payload["response_format"] = {"type": "json_object"}

        try:
            response: httpx.Response = await self._client.post(
                "/v1/chat/completions",
                headers={"Authorization": f"Bearer {self._api_key}"},
                json=payload,
            )
        except httpx.TimeoutException as exc:
            raise LLMTimeoutError(f"Timeout Mistral apres appel : {exc}") from exc
        except httpx.RequestError as exc:
            raise LLMTransientError(f"Erreur reseau Mistral : {exc}") from exc

        if response.status_code in _TRANSIENT_STATUS:
            raise LLMTransientError(
                f"Mistral a repondu {response.status_code} (temporaire)."
            )
        if response.status_code >= 400:
            raise LLMError(
                f"Mistral a repondu {response.status_code} : {response.text[:300]}"
            )

        return _parse_mistral_response(response.json(), self.model)

    async def aclose(self) -> None:
        await self._client.aclose()


def _parse_mistral_response(data: dict[str, object], model: str) -> LLMResponse:
    """Extrait le texte et les metadonnees d'une reponse Mistral."""
    choices = data.get("choices")
    if not isinstance(choices, list) or not choices:
        raise LLMError("Reponse Mistral sans 'choices'.")

    first = choices[0]
    if not isinstance(first, dict):
        raise LLMError("Reponse Mistral malformee.")

    message = first.get("message")
    text: str = ""
    if isinstance(message, dict):
        content = message.get("content")
        if isinstance(content, str):
            text = content

    if not text.strip():
        raise LLMError("Reponse Mistral vide.")

    finish_reason = first.get("finish_reason")
    truncated: bool = finish_reason == "length"

    usage_raw = data.get("usage")
    usage: dict[str, int] = {}
    if isinstance(usage_raw, dict):
        for key in ("prompt_tokens", "completion_tokens", "total_tokens"):
            value = usage_raw.get(key)
            if isinstance(value, int):
                usage[key] = value

    return LLMResponse(
        text=text,
        model=model,
        provider=MistralProvider.name,
        truncated=truncated,
        usage=usage,
    )


# Verification statique : MistralProvider satisfait le protocole.
_: type[LLMProvider] = MistralProvider
