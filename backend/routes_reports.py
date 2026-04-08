"""Routes de gestion des comptes-rendus : sauvegarde, historique, feedback, corrections."""

import json
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from auth import get_current_user
from database import get_db_session
from db_models import User, Report, AuditLog

router = APIRouter(prefix="/reports", tags=["reports"])


# ---------------------------------------------------------------------------
# Modeles
# ---------------------------------------------------------------------------


class SaveReportRequest(BaseModel):
    """Requete de sauvegarde d'un CR."""
    raw_transcription: str
    structured_report: str
    organe_detecte: str = "non_determine"
    completeness_warnings: str = ""


class UpdateReportRequest(BaseModel):
    """Requete de modification d'un CR (stocke le diff)."""
    structured_report: str


class FeedbackRequest(BaseModel):
    """Requete de feedback sur un CR."""
    rating: int  # 1 a 5 etoiles
    comment: str = ""


class ReportSummary(BaseModel):
    """Resume d'un CR pour la liste."""
    id: str
    organe_detecte: str
    status: str
    created_at: str
    updated_at: str
    excerpt: str  # premiers 100 caracteres de la conclusion
    has_feedback: bool
    rating: int | None


class ReportDetail(BaseModel):
    """Detail complet d'un CR."""
    id: str
    raw_transcription: str
    structured_report: str
    organe_detecte: str
    status: str
    completeness_warnings: str
    created_at: str
    updated_at: str
    feedback_rating: int | None
    feedback_comment: str | None
    corrections: list[dict[str, str]]


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("", response_model=dict[str, str])
async def save_report(
    req: SaveReportRequest,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession | None, Depends(get_db_session)],
) -> dict[str, str]:
    """Sauvegarde un nouveau CR en base."""
    if db is None:
        raise HTTPException(status_code=503, detail="Base de donnees non disponible")

    report = Report(
        user_id=user.id,
        org_id=user.organization_id,
        raw_transcription=req.raw_transcription,
        structured_report=req.structured_report,
        organe_detecte=req.organe_detecte,
        completeness_warnings=req.completeness_warnings,
        status="draft",
    )
    db.add(report)

    # Audit log
    audit = AuditLog(
        user_id=user.id,
        action="report_created",
        details=f"Organe: {req.organe_detecte}",
    )
    db.add(audit)

    await db.commit()
    await db.refresh(report)

    return {"id": str(report.id), "status": "saved"}


@router.get("", response_model=list[ReportSummary])
async def list_reports(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession | None, Depends(get_db_session)],
) -> list[ReportSummary]:
    """Liste les CR de l'utilisateur, du plus recent au plus ancien."""
    if db is None:
        raise HTTPException(status_code=503, detail="Base de donnees non disponible")

    result = await db.execute(
        select(Report)
        .where(Report.user_id == user.id)
        .order_by(desc(Report.created_at))
        .limit(100)
    )
    reports: list[Report] = list(result.scalars().all())

    summaries: list[ReportSummary] = []
    for r in reports:
        # Extraire un extrait de la conclusion
        lines = r.structured_report.split("\n")
        excerpt: str = ""
        for line in reversed(lines):
            stripped = line.strip().replace("*", "").replace("_", "")
            if stripped and "conclusion" not in stripped.lower():
                excerpt = stripped[:100]
                break

        # Recuperer le feedback s'il existe
        feedback_data = _parse_feedback(r.completeness_warnings)

        summaries.append(ReportSummary(
            id=str(r.id),
            organe_detecte=r.organe_detecte,
            status=r.status,
            created_at=r.created_at.isoformat() if r.created_at else "",
            updated_at=r.updated_at.isoformat() if r.updated_at else "",
            excerpt=excerpt,
            has_feedback=feedback_data.get("rating") is not None,
            rating=feedback_data.get("rating"),
        ))

    return summaries


@router.get("/{report_id}", response_model=ReportDetail)
async def get_report(
    report_id: str,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession | None, Depends(get_db_session)],
) -> ReportDetail:
    """Recupere le detail complet d'un CR."""
    if db is None:
        raise HTTPException(status_code=503, detail="Base de donnees non disponible")

    result = await db.execute(
        select(Report).where(Report.id == report_id, Report.user_id == user.id)
    )
    report: Report | None = result.scalar_one_or_none()

    if report is None:
        raise HTTPException(status_code=404, detail="CR non trouve")

    feedback_data = _parse_feedback(report.completeness_warnings)
    corrections = _parse_corrections(report.completeness_warnings)

    return ReportDetail(
        id=str(report.id),
        raw_transcription=report.raw_transcription,
        structured_report=report.structured_report,
        organe_detecte=report.organe_detecte,
        status=report.status,
        completeness_warnings=report.completeness_warnings or "",
        created_at=report.created_at.isoformat() if report.created_at else "",
        updated_at=report.updated_at.isoformat() if report.updated_at else "",
        feedback_rating=feedback_data.get("rating"),
        feedback_comment=feedback_data.get("comment"),
        corrections=corrections,
    )


@router.put("/{report_id}")
async def update_report(
    report_id: str,
    req: UpdateReportRequest,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession | None, Depends(get_db_session)],
) -> dict[str, str]:
    """Met a jour un CR et stocke le diff pour amelioration continue."""
    if db is None:
        raise HTTPException(status_code=503, detail="Base de donnees non disponible")

    result = await db.execute(
        select(Report).where(Report.id == report_id, Report.user_id == user.id)
    )
    report: Report | None = result.scalar_one_or_none()

    if report is None:
        raise HTTPException(status_code=404, detail="CR non trouve")

    # Stocker le diff (ancien -> nouveau) pour amelioration continue
    old_report: str = report.structured_report
    if old_report != req.structured_report:
        correction: dict[str, str] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "before": old_report,
            "after": req.structured_report,
        }
        existing_data = _parse_all_metadata(report.completeness_warnings)
        corrections = existing_data.get("corrections", [])
        corrections.append(correction)
        existing_data["corrections"] = corrections
        report.completeness_warnings = json.dumps(existing_data, ensure_ascii=False)

    report.structured_report = req.structured_report
    report.updated_at = datetime.now(timezone.utc)

    # Audit log
    audit = AuditLog(
        user_id=user.id,
        action="report_updated",
        details=f"Report {report_id}",
    )
    db.add(audit)

    await db.commit()

    return {"status": "updated"}


@router.post("/{report_id}/feedback")
async def add_feedback(
    report_id: str,
    req: FeedbackRequest,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession | None, Depends(get_db_session)],
) -> dict[str, str]:
    """Ajoute un feedback (etoiles + commentaire) a un CR."""
    if db is None:
        raise HTTPException(status_code=503, detail="Base de donnees non disponible")

    if req.rating < 1 or req.rating > 5:
        raise HTTPException(status_code=400, detail="Note entre 1 et 5")

    result = await db.execute(
        select(Report).where(Report.id == report_id, Report.user_id == user.id)
    )
    report: Report | None = result.scalar_one_or_none()

    if report is None:
        raise HTTPException(status_code=404, detail="CR non trouve")

    existing_data = _parse_all_metadata(report.completeness_warnings)
    existing_data["feedback"] = {
        "rating": req.rating,
        "comment": req.comment,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    report.completeness_warnings = json.dumps(existing_data, ensure_ascii=False)

    # Audit log
    audit = AuditLog(
        user_id=user.id,
        action="feedback_added",
        details=f"Report {report_id}, rating={req.rating}",
    )
    db.add(audit)

    await db.commit()

    return {"status": "feedback_saved"}


@router.delete("/{report_id}")
async def delete_report(
    report_id: str,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession | None, Depends(get_db_session)],
) -> dict[str, str]:
    """Supprime un CR (droit a l'effacement RGPD)."""
    if db is None:
        raise HTTPException(status_code=503, detail="Base de donnees non disponible")

    result = await db.execute(
        select(Report).where(Report.id == report_id, Report.user_id == user.id)
    )
    report: Report | None = result.scalar_one_or_none()

    if report is None:
        raise HTTPException(status_code=404, detail="CR non trouve")

    await db.delete(report)

    audit = AuditLog(
        user_id=user.id,
        action="report_deleted",
        details=f"Report {report_id} supprime (RGPD)",
    )
    db.add(audit)

    await db.commit()
    return {"status": "deleted"}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _parse_all_metadata(raw: str | None) -> dict[str, object]:
    """Parse les metadonnees stockees dans completeness_warnings."""
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return {}


def _parse_feedback(raw: str | None) -> dict[str, object]:
    """Extrait le feedback depuis les metadonnees."""
    data = _parse_all_metadata(raw)
    feedback = data.get("feedback")
    if isinstance(feedback, dict):
        return feedback
    return {}


def _parse_corrections(raw: str | None) -> list[dict[str, str]]:
    """Extrait les corrections depuis les metadonnees."""
    data = _parse_all_metadata(raw)
    corrections = data.get("corrections")
    if isinstance(corrections, list):
        return corrections
    return []
