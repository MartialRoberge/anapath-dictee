"""Routes d'administration : vue globale des CR, feedbacks, corrections, stats."""

import json
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select, desc, func
from sqlalchemy.ext.asyncio import AsyncSession

from auth import get_admin_user
from database import get_db_session
from db_models import User, Report, AuditLog

router = APIRouter(prefix="/admin", tags=["admin"])


# ---------------------------------------------------------------------------
# Modeles
# ---------------------------------------------------------------------------


class AdminReportSummary(BaseModel):
    """Resume d'un CR pour l'admin."""
    id: str
    user_name: str
    user_email: str
    organe_detecte: str
    status: str
    created_at: str
    rating: int | None
    feedback_comment: str | None
    correction_count: int


class AdminStats(BaseModel):
    """Statistiques globales pour le dashboard admin."""
    total_reports: int
    total_users: int
    average_rating: float | None
    reports_with_feedback: int
    reports_with_corrections: int
    reports_by_organ: dict[str, int]


class AdminCorrection(BaseModel):
    """Une correction faite par un praticien."""
    report_id: str
    user_name: str
    organe: str
    timestamp: str
    before_excerpt: str
    after_excerpt: str


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/reports", response_model=list[AdminReportSummary])
async def admin_list_reports(
    _user: Annotated[User, Depends(get_admin_user)],
    db: Annotated[AsyncSession | None, Depends(get_db_session)],
) -> list[AdminReportSummary]:
    """Liste tous les CR de tous les utilisateurs (admin only)."""
    if db is None:
        raise HTTPException(status_code=503, detail="Base de donnees non disponible")

    result = await db.execute(
        select(Report, User)
        .join(User, Report.user_id == User.id)
        .order_by(desc(Report.created_at))
        .limit(200)
    )
    rows = result.all()

    summaries: list[AdminReportSummary] = []
    for report, user in rows:
        metadata = _parse_metadata(report.completeness_warnings)
        feedback = metadata.get("feedback", {})
        corrections = metadata.get("corrections", [])

        summaries.append(AdminReportSummary(
            id=str(report.id),
            user_name=user.name,
            user_email=user.email,
            organe_detecte=report.organe_detecte,
            status=report.status,
            created_at=report.created_at.isoformat() if report.created_at else "",
            rating=feedback.get("rating") if isinstance(feedback, dict) else None,
            feedback_comment=feedback.get("comment") if isinstance(feedback, dict) else None,
            correction_count=len(corrections) if isinstance(corrections, list) else 0,
        ))

    return summaries


@router.get("/stats", response_model=AdminStats)
async def admin_stats(
    _user: Annotated[User, Depends(get_admin_user)],
    db: Annotated[AsyncSession | None, Depends(get_db_session)],
) -> AdminStats:
    """Statistiques globales pour piloter le produit."""
    if db is None:
        raise HTTPException(status_code=503, detail="Base de donnees non disponible")

    # Comptages
    total_reports_result = await db.execute(select(func.count(Report.id)))
    total_reports: int = total_reports_result.scalar() or 0

    total_users_result = await db.execute(select(func.count(User.id)))
    total_users: int = total_users_result.scalar() or 0

    # Recuperer tous les rapports pour analyser les metadata
    all_reports_result = await db.execute(select(Report))
    all_reports: list[Report] = list(all_reports_result.scalars().all())

    ratings: list[int] = []
    reports_with_feedback: int = 0
    reports_with_corrections: int = 0
    organ_counts: dict[str, int] = {}

    for report in all_reports:
        # Organe
        organe: str = report.organe_detecte or "non_determine"
        organ_counts[organe] = organ_counts.get(organe, 0) + 1

        # Metadata
        metadata = _parse_metadata(report.completeness_warnings)
        feedback = metadata.get("feedback")
        corrections = metadata.get("corrections")

        if isinstance(feedback, dict) and feedback.get("rating"):
            ratings.append(int(feedback["rating"]))
            reports_with_feedback += 1

        if isinstance(corrections, list) and len(corrections) > 0:
            reports_with_corrections += 1

    average_rating: float | None = (
        sum(ratings) / len(ratings) if ratings else None
    )

    return AdminStats(
        total_reports=total_reports,
        total_users=total_users,
        average_rating=round(average_rating, 1) if average_rating else None,
        reports_with_feedback=reports_with_feedback,
        reports_with_corrections=reports_with_corrections,
        reports_by_organ=organ_counts,
    )


@router.get("/corrections", response_model=list[AdminCorrection])
async def admin_corrections(
    _user: Annotated[User, Depends(get_admin_user)],
    db: Annotated[AsyncSession | None, Depends(get_db_session)],
) -> list[AdminCorrection]:
    """Liste toutes les corrections faites par les praticiens (pour amelioration continue)."""
    if db is None:
        raise HTTPException(status_code=503, detail="Base de donnees non disponible")

    result = await db.execute(
        select(Report, User)
        .join(User, Report.user_id == User.id)
        .order_by(desc(Report.updated_at))
        .limit(200)
    )
    rows = result.all()

    corrections: list[AdminCorrection] = []
    for report, user in rows:
        metadata = _parse_metadata(report.completeness_warnings)
        report_corrections = metadata.get("corrections", [])

        if not isinstance(report_corrections, list):
            continue

        for correction in report_corrections:
            if not isinstance(correction, dict):
                continue
            before: str = correction.get("before", "")
            after: str = correction.get("after", "")
            corrections.append(AdminCorrection(
                report_id=str(report.id),
                user_name=user.name,
                organe=report.organe_detecte,
                timestamp=correction.get("timestamp", ""),
                before_excerpt=before[:200] + "..." if len(before) > 200 else before,
                after_excerpt=after[:200] + "..." if len(after) > 200 else after,
            ))

    return corrections


@router.get("/audit", response_model=list[dict[str, str | None]])
async def admin_audit(
    _user: Annotated[User, Depends(get_admin_user)],
    db: Annotated[AsyncSession | None, Depends(get_db_session)],
) -> list[dict[str, str | None]]:
    """Journal d'audit complet (ISO 15189)."""
    if db is None:
        raise HTTPException(status_code=503, detail="Base de donnees non disponible")

    result = await db.execute(
        select(AuditLog)
        .order_by(desc(AuditLog.created_at))
        .limit(500)
    )
    logs: list[AuditLog] = list(result.scalars().all())

    return [
        {
            "id": str(log.id),
            "user_id": str(log.user_id) if log.user_id else None,
            "action": log.action,
            "details": log.details,
            "ip": log.ip_address,
            "created_at": log.created_at.isoformat() if log.created_at else None,
        }
        for log in logs
    ]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _parse_metadata(raw: str | None) -> dict[str, object]:
    """Parse les metadonnees JSON."""
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return {}
