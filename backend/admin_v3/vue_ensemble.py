"""KPI et serie quotidienne unifies : v3 (telemetrie), ancienne version (reports), etude (etude_dossiers)."""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta, timezone
from statistics import median
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from db_models import Report, Signalement, TelemetrieEvenement, User
from etude.models import EtudeDossier, EtudeSession

from .signalements import en_utc

PERIODES = {"7j": 7, "30j": 30, "90j": 90, "tout": None}
MAX_JOURS_SERIE = 366


def _jour(d: datetime) -> str:
    return en_utc(d).astimezone(timezone.utc).date().isoformat()  # type: ignore[union-attr]


async def _existe(db: AsyncSession, colonne: Any) -> bool:
    return (await db.execute(select(colonne).limit(1))).first() is not None


async def calculer(db: AsyncSession, periode: str, maintenant: datetime | None = None) -> dict[str, Any]:
    now = maintenant or datetime.now(timezone.utc)
    jours = PERIODES[periode]
    debut: datetime | None = None
    if jours is not None:
        debut = (now - timedelta(days=jours - 1)).replace(hour=0, minute=0, second=0, microsecond=0)

    def borne(col: Any) -> list[Any]:
        return [col >= debut] if debut is not None else []

    tele = [(u, t, en_utc(ts)) for u, t, ts in (await db.execute(
        select(TelemetrieEvenement.user_id, TelemetrieEvenement.type, TelemetrieEvenement.ts)
        .where(*borne(TelemetrieEvenement.ts)))).all()]
    durees = [p.get("duree_ms") for (p,) in (await db.execute(
        select(TelemetrieEvenement.payload).where(TelemetrieEvenement.type == "projet_genere", *borne(TelemetrieEvenement.ts)))).all()
        if isinstance(p, dict) and isinstance(p.get("duree_ms"), (int, float))]
    reports = [(u, en_utc(ts)) for u, ts in (await db.execute(
        select(Report.user_id, Report.created_at).where(*borne(Report.created_at)))).all()]
    dossiers = [(u, en_utc(ts)) for u, ts in (await db.execute(
        select(EtudeSession.praticien_id, EtudeDossier.cree_a)
        .join(EtudeSession, EtudeDossier.session_id == EtudeSession.id, isouter=True)
        .where(*borne(EtudeDossier.cree_a)))).all()]

    projets = [r for r in tele if r[1] == "projet_genere"]
    edits = sum(1 for r in tele if r[1] == "element_edite")
    actifs = {u for u, _, _ in tele} | {u for u, _ in reports} | {u for u, _ in dossiers}
    actifs.discard(None)

    # --- serie quotidienne
    toutes_dates = [ts for _, _, ts in tele if ts] + [ts for _, ts in reports if ts] + [ts for _, ts in dossiers if ts]
    if jours is None:
        premier = min(toutes_dates) if toutes_dates else now
        nb = min(MAX_JOURS_SERIE, (now.date() - premier.date()).days + 1)
    else:
        nb = jours
    liste = [(now.date() - timedelta(days=nb - 1 - i)).isoformat() for i in range(nb)]
    par_jour: dict[str, dict[str, Any]] = {j: {"p": 0, "r": 0, "u": set()} for j in liste}
    for u, t, ts in tele:
        c = par_jour.get(_jour(ts)) if ts else None
        if c is not None:
            c["u"].add(u)
            c["p"] += t == "projet_genere"
    for u, ts in reports:
        c = par_jour.get(_jour(ts)) if ts else None
        if c is not None:
            c["r"] += 1
            c["u"].add(u)
    for u, ts in dossiers:
        c = par_jour.get(_jour(ts)) if ts else None
        if c is not None and u:
            c["u"].add(u)

    fb = defaultdict(int)
    sens = (await db.execute(
        select(TelemetrieEvenement.payload).where(TelemetrieEvenement.type == "feedback", *borne(TelemetrieEvenement.ts)))).all()
    for (p,) in sens:
        if isinstance(p, dict):
            fb[p.get("sens")] += 1

    ouverts = (await db.execute(select(func.count()).select_from(Signalement).where(
        Signalement.statut.in_(("ouvert", "en_cours")), Signalement.doublon_de.is_(None)))).scalar_one()
    total_users = (await db.execute(select(func.count()).select_from(User))).scalar_one()

    return {
        "periode": periode,
        "kpi": {
            "utilisateurs_actifs": len(actifs),
            "utilisateurs_total": total_users,
            "projets_v3": len(projets),
            "comptes_rendus_anciens": len(reports),
            "dossiers_etude": len(dossiers),
            "notes_utile": fb["positif"],
            "notes_a_ameliorer": fb["negatif"],
            "signalements_ouverts": ouverts,
            "duree_mediane_generation_ms": round(float(median(durees)), 1) if durees else None,
            "modifications_moyennes_par_projet": round(edits / len(projets), 2) if projets else None,
        },
        "serie": [{"jour": j, "projets_v3": par_jour[j]["p"], "comptes_rendus_anciens": par_jour[j]["r"],
                   "utilisateurs_actifs": len(par_jour[j]["u"])} for j in liste],
        "origines": {
            "v3": await _existe(db, TelemetrieEvenement.id),
            "ancienne_version": await _existe(db, Report.id),
            "etude": await _existe(db, EtudeDossier.id),
        },
    }
