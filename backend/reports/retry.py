"""Retry avec backoff exponentiel pour les appels LLM/STT transitoires."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import TypeVar

from llm.base import LLMTransientError

logger = logging.getLogger("anapath.retry")

T = TypeVar("T")


async def with_retry(
    func: Callable[[], Awaitable[T]],
    *,
    max_retries: int,
    base_delay: float = 0.5,
    label: str = "appel",
) -> T:
    """Execute ``func`` en re-essayant sur ``LLMTransientError``.

    Backoff : base_delay * 2**tentative. Les erreurs non transitoires remontent
    immediatement.
    """
    attempt: int = 0
    while True:
        try:
            return await func()
        except LLMTransientError as exc:
            if attempt >= max_retries:
                logger.warning(
                    "%s: echec apres %d tentatives (%s)", label, attempt + 1, exc
                )
                raise
            delay: float = base_delay * (2**attempt)
            logger.info(
                "%s: erreur transitoire (%s), retry dans %.1fs", label, exc, delay
            )
            await asyncio.sleep(delay)
            attempt += 1
