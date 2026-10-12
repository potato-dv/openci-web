from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy.orm import Session

from app.models.assignment import InvestigationAssignment
from app.models.investigation import Investigation
from app.models.report import InvestigationReport
from app.models.review import InvestigationReview
from app.models.user import User
from app.schemas.investigation import InvestigationCreate, InvestigationUpdate


def create_investigation(
    db: Session,
    data: InvestigationCreate,
) -> Investigation:
    values = data.model_dump()
    investigation = Investigation(reference_number=f"INV-{uuid4().hex.upper()}", **values)

    db.add(investigation)
    db.commit()
    db.refresh(investigation)

    return investigation

def get_investigations(
    db: Session,
    current_user: User,
) -> list[Investigation]:
    query = db.query(Investigation)
    query = query.filter(Investigation.deleted_at.is_(None))

    if current_user.role == "agent":
        query = query.filter(Investigation.assigned_agent_id == current_user.id)

    return query.order_by(Investigation.created_at.desc()).all()

def get_investigation(
    db: Session,
    investigation_id: int,
) -> Investigation | None:
    return (
        db.query(Investigation)
        .filter(Investigation.id == investigation_id, Investigation.deleted_at.is_(None))
        .first()
    )

def update_investigation(
    db: Session,
    investigation: Investigation,
    data: InvestigationUpdate,
) -> Investigation:
    update_data = data.model_dump(exclude_unset=True)

    for field, value in update_data.items():
        setattr(investigation, field, value)

    db.commit()
    db.refresh(investigation)

    return investigation


def can_access_investigation(
    investigation: Investigation,
    current_user: User,
) -> bool:
    return current_user.role in {"admin", "supervisor"} or (
        current_user.role == "agent"
        and investigation.assigned_agent_id == current_user.id
    )


def is_valid_status_transition(
    current_status: str,
    next_status: str,
) -> bool:
    allowed_transitions = {
        "pending": {"assigned"},
        "assigned": {"in_progress"},
        "in_progress": {"under_review"},
        "under_review": {"completed", "returned_for_correction"},
        "returned_for_correction": {"in_progress"},
        "completed": set(),
    }

    return next_status in allowed_transitions.get(current_status, set())


def get_assignment_history(
    db: Session,
    investigation_id: int,
) -> list[InvestigationAssignment]:
    return (
        db.query(InvestigationAssignment)
        .filter(InvestigationAssignment.investigation_id == investigation_id)
        .order_by(InvestigationAssignment.assigned_at.desc())
        .all()
    )


def assign_investigation(
    db: Session,
    investigation: Investigation,
    agent: User,
    assigned_by: User,
    note: str | None,
) -> InvestigationAssignment:
    if investigation.status not in {"pending", "assigned"}:
        raise ValueError("Only pending or assigned investigations can be assigned")

    active_assignment = (
        db.query(InvestigationAssignment)
        .filter(
            InvestigationAssignment.investigation_id == investigation.id,
            InvestigationAssignment.is_active.is_(True),
        )
        .first()
    )

    if not agent.is_active:
        raise ValueError("Inactive agents cannot receive investigations")

    if active_assignment and active_assignment.agent_id == agent.id:
        active_assignment.note = note
        db.commit()
        db.refresh(active_assignment)
        return active_assignment

    if active_assignment:
        active_assignment.is_active = False
        active_assignment.unassigned_at = datetime.now(timezone.utc)

    assignment = InvestigationAssignment(
        investigation_id=investigation.id,
        agent_id=agent.id,
        assigned_by_id=assigned_by.id,
        note=note,
    )
    investigation.assigned_agent_id = agent.id
    investigation.status = "assigned"

    db.add(assignment)
    db.commit()
    db.refresh(assignment)

    return assignment


def get_report(
    db: Session,
    investigation_id: int,
) -> InvestigationReport | None:
    return (
        db.query(InvestigationReport)
        .filter(InvestigationReport.investigation_id == investigation_id)
        .order_by(InvestigationReport.version.desc())
        .first()
    )


def get_report_versions(
    db: Session,
    investigation_id: int,
) -> list[InvestigationReport]:
    return (
        db.query(InvestigationReport)
        .filter(InvestigationReport.investigation_id == investigation_id)
        .order_by(InvestigationReport.version.desc())
        .all()
    )


def save_report_draft(
    db: Session,
    investigation: Investigation,
    author: User,
    data: ReportUpsert,
) -> InvestigationReport:
    report = get_report(db, investigation.id)

    if report is not None and report.status in {"submitted", "approved"}:
        raise ValueError("Submitted or approved report versions cannot be edited")

    starts_correction_revision = report is not None and (
        report.status == "returned_for_correction"
        or (investigation.status == "returned_for_correction" and report.status == "draft")
    )
    if report is None or starts_correction_revision:
        report = InvestigationReport(
            investigation_id=investigation.id,
            author_id=author.id,
            version=1 if report is None else report.version + 1,
            **data.model_dump(),
        )
        db.add(report)
    else:
        for field, value in data.model_dump().items():
            setattr(report, field, value)

    if investigation.status in {"assigned", "returned_for_correction"}:
        investigation.status = "in_progress"

    db.commit()
    db.refresh(report)
    return report


def submit_report(
    db: Session,
    investigation: Investigation,
) -> InvestigationReport:
    report = get_report(db, investigation.id)

    if report is None or not report.content.strip():
        raise ValueError("A non-empty report draft is required before submission")

    if report.status != "draft":
        raise ValueError("Only a draft report version can be submitted")

    if not report.visit_outcome:
        raise ValueError("Select a visit outcome before submitting the report")
    if not report.outcome:
        raise ValueError("Select an investigation outcome before submitting the report")
    if report.visit_outcome in {"visited", "no_access"} and report.visited_at is None:
        raise ValueError("Visit date and time are required for this visit outcome")
    if report.outcome == "verified" and not (report.verified_address or "").strip():
        raise ValueError("Verified address is required for a verified outcome")

    if investigation.status not in {"in_progress", "returned_for_correction"}:
        raise ValueError("Investigation is not ready for report submission")

    report.status = "submitted"
    report.submitted_at = datetime.now(timezone.utc)
    investigation.status = "under_review"

    db.commit()
    db.refresh(report)
    return report


def get_review_history(
    db: Session,
    investigation_id: int,
) -> list[InvestigationReview]:
    return (
        db.query(InvestigationReview)
        .filter(InvestigationReview.investigation_id == investigation_id)
        .order_by(InvestigationReview.reviewed_at.desc())
        .all()
    )


def review_investigation_report(
    db: Session,
    investigation: Investigation,
    reviewer: User,
    decision: str,
    comments: str | None,
) -> InvestigationReview:
    report = get_report(db, investigation.id)

    if report is None or report.status != "submitted":
        raise ValueError("A submitted report is required for review")

    if investigation.status != "under_review":
        raise ValueError("Investigation is not awaiting review")

    if decision == "returned_for_correction" and not comments:
        raise ValueError("Comments are required when returning a report")

    review = InvestigationReview(
        investigation_id=investigation.id,
        report_id=report.id,
        reviewer_id=reviewer.id,
        decision=decision,
        comments=comments,
    )

    if decision == "approved":
        report.status = "approved"
        investigation.status = "completed"
    else:
        report.status = "returned_for_correction"
        investigation.status = "returned_for_correction"

    db.add(review)
    db.commit()
    db.refresh(review)
    return review

def delete_investigation(
    db: Session,
    investigation: Investigation,
) -> None:
    investigation.deleted_at = datetime.now(timezone.utc)
    db.commit()
