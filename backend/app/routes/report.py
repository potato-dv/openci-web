from typing import Literal
from fastapi import APIRouter, Depends, Query
from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload
from app.database.session import get_db
from app.models.investigation import Investigation
from app.models.report import InvestigationReport
from app.models.user import User
from app.schemas.report import ReportQueueResponse
from app.services.search import investigation_search
from app.utils.auth import require_roles

router = APIRouter(prefix="/reports", tags=["Reports"])


@router.get("/review-queue", response_model=ReportQueueResponse)
def review_queue(
    status: Literal["submitted", "returned_for_correction", "approved"] = "submitted",
    q: str = "", page: int = Query(default=1, ge=1), page_size: int = Query(default=25, ge=1, le=100),
    sort: Literal["submitted_at", "updated_at", "reference_number"] = "submitted_at",
    direction: Literal["asc", "desc"] = "asc",
    db: Session = Depends(get_db), _: User = Depends(require_roles("admin", "supervisor")),
):
    latest = db.query(InvestigationReport.investigation_id, func.max(InvestigationReport.version).label("version")).group_by(InvestigationReport.investigation_id).subquery()
    query = db.query(InvestigationReport, Investigation).join(latest, (latest.c.investigation_id == InvestigationReport.investigation_id) & (latest.c.version == InvestigationReport.version)).join(Investigation, Investigation.id == InvestigationReport.investigation_id).filter(Investigation.deleted_at.is_(None), InvestigationReport.status == status)
    if q.strip():
        query = query.filter(investigation_search(q))
    total = query.count()
    column = Investigation.reference_number if sort == "reference_number" else getattr(InvestigationReport, sort)
    rows = query.options(joinedload(InvestigationReport.author), joinedload(Investigation.assigned_agent)).order_by(column.desc() if direction == "desc" else column.asc(), InvestigationReport.id).offset((page-1)*page_size).limit(page_size).all()
    return {"total": total, "page": page, "page_size": page_size, "items": [{"report_id": report.id, "investigation_id": case.id, "reference_number": case.reference_number, "subject_name": case.subject_name, "assigned_agent_name": case.assigned_agent_name, "author_name": report.author_name, "version": report.version, "priority": case.priority, "status": report.status, "submitted_at": report.submitted_at, "updated_at": report.updated_at} for report, case in rows]}
