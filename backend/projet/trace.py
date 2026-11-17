"""Trace d'execution reelle : une ``TraceStep`` par agent, emise a chaque changement d'etat.

Le traceur chronometre chaque etape (``debut_ms`` relatif au lancement du
pipeline, ``duree_ms``) et pousse une copie de l'etape vers un callback a chaque
transition (en_cours -> ok/avertissement/erreur/saute). C'est ce flux qui
alimente l'evenement SSE ``step`` : rien n'est decoratif.
"""
from __future__ import annotations

import time
from collections.abc import Awaitable, Callable
from contextlib import asynccontextmanager
from typing import AsyncIterator

from projet.schemas import Role, TraceStep

Emetteur = Callable[[str, dict[str, object]], Awaitable[None]]


async def _silencieux(_evt: str, _data: dict[str, object]) -> None:
    return None


class Traceur:
    def __init__(self, emettre: Emetteur | None = None) -> None:
        self._emettre: Emetteur = emettre or _silencieux
        self._t0 = time.perf_counter()
        self.etapes: list[TraceStep] = []
        self._chronos: dict[str, float] = {}

    def maintenant_ms(self) -> int:
        return int((time.perf_counter() - self._t0) * 1000)

    async def emettre(self, evenement: str, donnees: dict[str, object]) -> None:
        try:
            await self._emettre(evenement, donnees)
        except Exception:  # noqa: BLE001 - un client deconnecte ne casse pas le pipeline
            pass

    async def _pousser(self, etape: TraceStep) -> None:
        await self.emettre("step", etape.model_dump())

    async def ouvrir(self, id_: str, agent: str, role: Role, titre: str,
                     modele: str | None = None) -> TraceStep:
        etape = TraceStep(id=id_, agent=agent, role=role, titre=titre, statut="en_cours",
                          debut_ms=self.maintenant_ms(), modele=modele)
        self._chronos[id_] = time.perf_counter()
        self.etapes.append(etape)
        await self._pousser(etape)
        return etape

    async def fermer(self, etape: TraceStep, statut: str, resume: str,
                     details: list[str] | None = None, modele: str | None = None) -> None:
        etape.statut = statut  # type: ignore[assignment]
        etape.resume = resume
        if details is not None:
            etape.details = [d for d in details if d][:40]
        if modele is not None:
            etape.modele = modele
        debut = self._chronos.get(etape.id, time.perf_counter())
        etape.duree_ms = int((time.perf_counter() - debut) * 1000)
        await self._pousser(etape)

    async def sauter(self, id_: str, agent: str, role: Role, titre: str, raison: str) -> TraceStep:
        """Etape non executee (pas d'audio, ressource absente...) : tracee quand meme."""
        etape = TraceStep(id=id_, agent=agent, role=role, titre=titre, statut="saute",
                          debut_ms=self.maintenant_ms(), duree_ms=0, resume=raison)
        self.etapes.append(etape)
        await self._pousser(etape)
        return etape

    @asynccontextmanager
    async def etape(self, id_: str, agent: str, role: Role, titre: str,
                    modele: str | None = None) -> AsyncIterator[TraceStep]:
        """Contexte : ouvre l'etape ; la ferme en 'erreur' si une exception s'echappe."""
        e = await self.ouvrir(id_, agent, role, titre, modele)
        try:
            yield e
        except Exception as exc:
            if e.statut == "en_cours":
                await self.fermer(e, "erreur", f"Échec : {type(exc).__name__}", [str(exc)[:300]])
            raise
        if e.statut == "en_cours":
            await self.fermer(e, "ok", e.resume or "Termine")
