"""Routes telemetrie v3 : collecte whitelistee (/v3/telemetrie) et vues admin (/v3/admin/telemetrie)."""

import hashlib
import logging
from datetime import datetime, timedelta, timezone
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from auth import get_admin_user, get_current_user
from config import get_settings
from database import get_db_session
from db_models import TelemetrieEvenement, User
from rate_limit import limiter

from . import agregations
from .whitelist import Rejet, valider_evenement

logger = logging.getLogger("anapath.telemetrie")
router = APIRouter(prefix="/v3", tags=["telemetrie"])

MAX_LOT = 50


class EvenementIn(BaseModel):
    """Evenement brut : le contenu est valide a la main par la whitelist, pas par pydantic."""
    type: str
    payload: dict[str, Any] = Field(default_factory=dict)
    projet_id: str | None = None


class LotIn(BaseModel):
    evenements: list[EvenementIn] = Field(max_length=MAX_LOT)


class LotOut(BaseModel):
    acceptes: int
    rejetes: int


def hacher_projet(projet_id: str) -> str:
    """Hash sale irreversible : le serveur ne retient jamais l'id de projet en clair."""
    sel = get_settings().jwt_secret
    return hashlib.sha256(f"{sel}:{projet_id}".encode()).hexdigest()[:16]


@router.post("/telemetrie/evenements", response_model=LotOut)
@limiter.limit("60/minute")
async def recevoir_evenements(
    request: Request,
    lot: LotIn,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession | None, Depends(get_db_session)],
) -> LotOut:
    """Enregistre un lot d'evenements. Chaque evenement non conforme est rejete (compte, jamais stocke)."""
    if db is None:
        raise HTTPException(status_code=503, detail="Base de données non disponible")
    ok, ko = 0, 0
    for ev in lot.evenements:
        try:
            type_, payload, projet_id = valider_evenement(ev.type, ev.payload, ev.projet_id)
        except Rejet:
            ko += 1
            continue
        db.add(TelemetrieEvenement(
            user_id=user.id, type=type_, payload=payload,
            projet_hash=hacher_projet(projet_id) if projet_id else None,
            ts=datetime.now(timezone.utc),
        ))
        ok += 1
    if ok:
        await db.commit()
    return LotOut(acceptes=ok, rejetes=ko)


Periode = Literal["7j", "30j", "90j"]


async def _charger(db: AsyncSession, jours: int, maintenant: datetime) -> tuple[list[dict], dict[str, str]]:
    remonter = max(2 * jours, 30)
    depuis = maintenant - timedelta(days=remonter)
    res = await db.execute(select(TelemetrieEvenement).where(TelemetrieEvenement.ts > depuis))
    lignes = []
    for e in res.scalars():
        ts = e.ts if e.ts.tzinfo else e.ts.replace(tzinfo=timezone.utc)
        lignes.append({"user_id": e.user_id, "type": e.type, "projet_hash": e.projet_hash, "ts": ts, "payload": e.payload or {}})
    ids = {r["user_id"] for r in lignes}
    emails: dict[str, str] = {}
    if ids:
        res = await db.execute(select(User.id, User.email).where(User.id.in_(ids)))
        emails = {i: m for i, m in res.all()}
    return lignes, emails


async def _synthese(db: AsyncSession | None, periode: str) -> dict[str, Any]:
    if db is None:
        raise HTTPException(status_code=503, detail="Base de données non disponible")
    jours = int(periode[:-1])
    maintenant = datetime.now(timezone.utc)
    lignes, emails = await _charger(db, jours, maintenant)
    return agregations.synthese(lignes, jours, maintenant, emails)


@router.get("/admin/telemetrie/synthese")
async def synthese(
    _admin: Annotated[User, Depends(get_admin_user)],
    db: Annotated[AsyncSession | None, Depends(get_db_session)],
    periode: Periode = "7j",
) -> dict[str, Any]:
    """KPI, series quotidiennes et repartitions sur la periode (admin uniquement)."""
    return await _synthese(db, periode)


@router.get("/admin/telemetrie/recommandations")
async def recommandations(
    _admin: Annotated[User, Depends(get_admin_user)],
    db: Annotated[AsyncSession | None, Depends(get_db_session)],
    periode: Periode = "30j",
) -> dict[str, Any]:
    """Actions concretes calculees a partir de la synthese (admin uniquement)."""
    s = await _synthese(db, periode)
    return {"periode_jours": s["periode_jours"], "recommandations": agregations.recommandations(s)}
