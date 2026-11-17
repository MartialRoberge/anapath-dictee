"""Client LLM des agents v3 : un modele par agent, retry, delai, compteurs.

Chaque agent nomme son modele (diversite : le relecteur n'utilise pas le meme
modele que le redacteur). Le client compte les appels et les jetons pour les
``Metriques`` du projet, applique un delai maximal par appel (``asyncio.wait_for``)
et re-essaie les erreurs transitoires (``reports/retry.py``).

Les tests injectent un faux client implementant ``ClientLLM`` : aucun appel
reseau n'est fait hors de la campagne live.
"""
from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Protocol

import httpx

from config import get_settings
from llm.base import LLMError, LLMResponse, LLMTimeoutError, LLMTransientError
from reports.guardrails import parse_llm_json
from reports.retry import with_retry

# Modeles par role (surchargeables par l'appelant).
# NB (15/11/2026) : l'alias « mistral-large-latest » pointe desormais vers
# mistral-large-4, un modele A RAISONNEMENT (blocs « thinking », plusieurs
# secondes de plus, temperature 0 refusee sans top_p=1). On epingle donc la
# derniere version large SANS raisonnement, mesuree a ~1 s sur une extraction.
MODELE_RAPIDE = "mistral-small-latest"      # correcteur (cas ambigus)
MODELE_EXTRACTION = "mistral-large-2512"    # extracteur
MODELE_REDACTION = "mistral-large-2512"     # redacteur
MODELE_RELECTURE = "mistral-medium-latest"  # relecteur (modele different du redacteur)


class ClientLLM(Protocol):
    """Interface minimale attendue par les agents."""

    async def completer(self, *, modele: str, systeme: str, utilisateur: str,
                        max_tokens: int, delai_s: float, temperature: float = 0.0) -> LLMResponse:
        ...


@dataclass
class Compteur:
    """Compteurs d'un passage de pipeline (metriques exposees au front)."""

    appels: int = 0
    tokens_entree: int = 0
    tokens_sortie: int = 0
    erreurs: int = 0
    durees_ms: dict[str, int] = field(default_factory=dict)

    def enregistrer(self, reponse: LLMResponse, etiquette: str, duree_ms: int) -> None:
        self.appels += 1
        self.tokens_entree += int(reponse.usage.get("prompt_tokens", 0))
        self.tokens_sortie += int(reponse.usage.get("completion_tokens", 0))
        self.durees_ms[etiquette] = duree_ms


class ClientMistral:
    """Implementation reelle : appel direct de l'API chat completions de Mistral.

    Pourquoi pas ``llm/mistral.py`` : depuis novembre 2026, ``mistral-large-latest``
    refuse ``temperature=0`` sans ``top_p=1`` (erreur 400 « greedy sampling »).
    Ce client envoie ``top_p=1`` explicitement et reutilise le mapping d'erreurs
    et le parseur de reponse de ``llm/`` (memes exceptions normalisees).
    """

    _http: httpx.AsyncClient | None = None

    @classmethod
    def _client(cls) -> httpx.AsyncClient:
        if cls._http is None:
            cls._http = httpx.AsyncClient(base_url="https://api.mistral.ai",
                                          timeout=get_settings().llm_timeout_seconds)
        return cls._http

    async def completer(self, *, modele: str, systeme: str, utilisateur: str,
                        max_tokens: int, delai_s: float, temperature: float = 0.0) -> LLMResponse:
        cle = get_settings().mistral_api_key
        if not cle:
            raise LLMError("MISTRAL_API_KEY absente : agents v3 indisponibles.")
        charge = {
            "model": modele, "temperature": temperature, "top_p": 1, "max_tokens": max_tokens,
            "response_format": {"type": "json_object"},
            "messages": [{"role": "system", "content": systeme}, {"role": "user", "content": utilisateur}],
        }
        try:
            r = await self._client().post("/v1/chat/completions", json=charge,
                                          headers={"Authorization": f"Bearer {cle}"}, timeout=delai_s + 5)
        except httpx.TimeoutException as exc:
            raise LLMTimeoutError(f"Timeout Mistral ({modele})") from exc
        except httpx.RequestError as exc:
            raise LLMTransientError(f"Erreur réseau Mistral : {type(exc).__name__}") from exc
        if r.status_code in _TRANSITOIRES:
            raise LLMTransientError(f"Mistral {r.status_code} (temporaire)")
        if r.status_code >= 400:
            raise LLMError(f"Mistral {r.status_code} : {r.text[:200]}")
        return _analyser_reponse(r.json(), modele)

    @classmethod
    async def fermer(cls) -> None:
        if cls._http is not None:
            await cls._http.aclose()
            cls._http = None


_TRANSITOIRES = frozenset({408, 409, 425, 429, 500, 502, 503, 504})


def _analyser_reponse(donnees: dict, modele: str) -> LLMResponse:
    """Texte + usage d'une reponse chat ; tolere un contenu en blocs (modeles a raisonnement)."""
    try:
        choix = donnees["choices"][0]
        contenu = choix["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise LLMError("Réponse Mistral malformée") from exc
    if isinstance(contenu, list):  # [{"type": "thinking", ...}, {"type": "text", "text": "..."}]
        contenu = "".join(b.get("text", "") for b in contenu if isinstance(b, dict) and b.get("type") == "text")
    if not isinstance(contenu, str) or not contenu.strip():
        raise LLMError("Réponse Mistral vide")
    usage = {k: v for k, v in (donnees.get("usage") or {}).items() if isinstance(v, int)}
    return LLMResponse(text=contenu, model=str(donnees.get("model") or modele), provider="mistral",
                       truncated=choix.get("finish_reason") == "length", usage=usage)


_client_defaut: ClientLLM | None = None


def get_client_llm() -> ClientLLM:
    """Dependance FastAPI : client LLM partage (remplace dans les tests)."""
    global _client_defaut
    if _client_defaut is None:
        _client_defaut = ClientMistral()
    return _client_defaut


async def appel_json(client: ClientLLM, compteur: Compteur, *, etiquette: str, modele: str,
                     systeme: str, utilisateur: str, max_tokens: int = 4096,
                     delai_s: float = 30.0, max_retries: int = 1) -> tuple[dict[str, object], LLMResponse]:
    """Appel JSON strict avec delai, retry transitoire et comptage.

    Leve ``LLMError`` (ou ``LLMTimeoutError``) si l'appel echoue definitivement ;
    l'orchestrateur traduit cela en etape 'avertissement'/'erreur' et se replie.
    """
    async def _une_fois() -> LLMResponse:
        try:
            return await asyncio.wait_for(
                client.completer(modele=modele, systeme=systeme, utilisateur=utilisateur,
                                 max_tokens=max_tokens, delai_s=delai_s),
                timeout=delai_s,
            )
        except asyncio.TimeoutError as exc:
            raise LLMTimeoutError(f"{etiquette} : délai de {delai_s:.0f} s dépassé") from exc

    t0 = time.perf_counter()
    try:
        reponse = await with_retry(_une_fois, max_retries=max_retries, base_delay=0.4, label=etiquette)
    except LLMError:
        compteur.erreurs += 1
        raise
    compteur.enregistrer(reponse, etiquette, int((time.perf_counter() - t0) * 1000))
    try:
        donnees = parse_llm_json(reponse.text)
    except ValueError as exc:
        compteur.erreurs += 1
        raise LLMError(f"{etiquette} : JSON inexploitable ({exc})") from exc
    if not isinstance(donnees, dict):
        raise LLMError(f"{etiquette} : JSON inattendu")
    return donnees, reponse
