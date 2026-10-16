from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from app.schemas.investigation import InvestigationCreate, InvestigationUpdate
from app.services.investigation import ( 
    assign_investigation,
    can_access_investigation,
    create_investigation,
    delete_investigation,
    permanently_delete_investigation,
    get_investigations,
    get_investigation,
    get_assignment_history,
    get_trashed_investigation,
    get_trashed_investigations,
    get_report,
    get_review_history,
    get_report_versions,
    review_investigation_report,
    restore_investigation,
    save_report_draft,
    submit_report,
    update_investigation,
    )

from fastapi import HTTPException, status
from app.models.user import User
from app.schemas.assignment import AssignmentCreate
from app.schemas.report import ReportUpsert
from app.schemas.review import ReviewCreate

def create(db: Session, data: InvestigationCreate, current_user: User):
    try:
        investigation = create_investigation(db, data)
    except IntegrityError as error:
        db.rollback()
        raise HTTPException(status_code=409, detail="Could not create investigation; please retry") from error
    from app.services.activity import record_activity

    record_activity(db, current_user, "investigation.created", "investigation", investigation.id)
    return investigation

def get_all(db: Session, current_user: User):
    return get_investigations(db, current_user)


def get_trash(db: Session):
    return get_trashed_investigations(db)


def restore(
    db: Session,
    investigation_id: int,
    current_user: User,
):
    if current_user.role not in {"admin", "supervisor"}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You do not have permission to restore investigations")

    investigation = get_trashed_investigation(db, investigation_id)
    if investigation is None:
        raise HTTPException(status_code=404, detail="Investigation not found in Trash")

    return restore_investigation(db, investigation, current_user)


def assign(
    db: Session,
    investigation_id: int,
    data: AssignmentCreate,
    current_user: User,
):
    investigation = get_one(db, investigation_id, current_user)

    agent = db.query(User).filter(User.id == data.agent_id).first()

    if agent is None:
        raise HTTPException(status_code=404, detail="Agent not found")

    if agent.role != "agent":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Investigation can only be assigned to an agent",
        )

    try:
        assignment = assign_investigation(
            db,
            investigation,
            agent,
            current_user,
            data.note,
        )
        from app.services.activity import record_activity

        record_activity(db, current_user, "investigation.assigned", "investigation", investigation.id, {"agent_id": agent.id})
        return assignment
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(error),
        ) from error
    except IntegrityError as error:
        db.rollback()
        raise HTTPException(status_code=409, detail="The investigation was assigned concurrently; refresh and try again") from error


def get_assignments(
    db: Session,
    investigation_id: int,
):
    return get_assignment_history(db, investigation_id)


def get_investigation_report(
    db: Session,
    investigation_id: int,
    current_user: User,
):
    investigation = get_one(db, investigation_id, current_user)
    report = get_report(db, investigation.id)
    return report


def get_investigation_report_versions(
    db: Session,
    investigation_id: int,
    current_user: User,
):
    investigation = get_one(db, investigation_id, current_user)
    return get_report_versions(db, investigation.id)


def save_investigation_report(
    db: Session,
    investigation_id: int,
    data: ReportUpsert,
    current_user: User,
):
    investigation = get_one(db, investigation_id, current_user)

    if current_user.role != "agent" or investigation.assigned_agent_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the assigned agent can edit this report",
        )

    try:
        report = save_report_draft(db, investigation, current_user, data)
        from app.services.activity import record_activity

        record_activity(db, current_user, "report.saved", "investigation", investigation.id)
        return report
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(error),
        ) from error


def submit_investigation_report(
    db: Session,
    investigation_id: int,
    current_user: User,
):
    investigation = get_one(db, investigation_id, current_user)

    if current_user.role != "agent" or investigation.assigned_agent_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the assigned agent can submit this report",
        )

    try:
        report = submit_report(db, investigation)
        from app.services.activity import record_activity

        record_activity(db, current_user, "report.submitted", "investigation", investigation.id)
        return report
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(error),
        ) from error


def review_report(
    db: Session,
    investigation_id: int,
    data: ReviewCreate,
    current_user: User,
):
    investigation = get_one(db, investigation_id, current_user)
    comments = data.comments.strip() if data.comments else None

    try:
        review = review_investigation_report(
            db,
            investigation,
            current_user,
            data.decision,
            comments,
        )
        from app.services.activity import record_activity

        record_activity(db, current_user, "report.reviewed", "investigation", investigation.id, {"decision": data.decision})
        return review
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(error),
        ) from error


def get_reviews(
    db: Session,
    investigation_id: int,
    current_user: User,
):
    get_one(db, investigation_id, current_user)
    return get_review_history(db, investigation_id)

def get_one(
    db: Session,
    investigation_id: int,
    current_user: User,
):
    investigation = get_investigation(db, investigation_id)

    if investigation is None:
        raise HTTPException(
            status_code=404,
            detail="Investigation not found",
        )

    if not can_access_investigation(investigation, current_user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have access to this investigation",
        )

    return investigation

def update(
    db: Session,
    investigation_id: int,
    data: InvestigationUpdate,
    current_user: User,
):
    investigation = get_investigation(db, investigation_id)

    if investigation is None:
        raise HTTPException(
            status_code=404,
            detail="Investigation not found",
        )

    if not can_access_investigation(investigation, current_user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have access to this investigation",
        )

    if current_user.role == "agent":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Agents cannot edit investigation details",
        )

    updated = update_investigation(db, investigation, data)
    from app.services.activity import record_activity

    record_activity(db, current_user, "investigation.updated", "investigation", investigation.id, {"fields": list(data.model_dump(exclude_unset=True))})
    return updated

def delete(
    db: Session,
    investigation_id: int,
    current_user: User,
):
    investigation = get_investigation(db, investigation_id)

    if investigation is None:
        raise HTTPException(
            status_code=404,
            detail="Investigation not found",
        )

    if current_user.role not in {"admin", "supervisor"}:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only admins and supervisors can move investigations to Trash",
        )

    delete_investigation(db, investigation, current_user)
    return {"message": "Investigation moved to Trash"}


def permanently_delete(
    db: Session,
    investigation_id: int,
    current_user: User,
):
    if current_user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only admins can permanently delete investigations")

    investigation = get_trashed_investigation(db, investigation_id)
    if investigation is None:
        raise HTTPException(status_code=404, detail="Investigation not found in Trash")

    permanently_delete_investigation(db, investigation, current_user)
