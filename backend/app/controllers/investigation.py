from sqlalchemy.orm import Session

from app.schemas.investigation import InvestigationCreate, InvestigationUpdate
from app.services.investigation import ( 
    assign_investigation,
    can_access_investigation,
    create_investigation,
    delete_investigation,
    get_investigations,
    get_investigation,
    get_assignment_history,
    get_report,
    get_review_history,
    is_valid_status_transition,
    review_investigation_report,
    save_report_draft,
    submit_report,
    update_investigation,
    )

from fastapi import HTTPException, status
from app.models.user import User
from app.schemas.assignment import AssignmentCreate
from app.schemas.report import ReportUpsert
from app.schemas.review import ReviewCreate

def create(db: Session, data: InvestigationCreate):
    return create_investigation(db, data)

def get_all(db: Session, current_user: User):
    return get_investigations(db, current_user)


def assign(
    db: Session,
    investigation_id: int,
    data: AssignmentCreate,
    current_user: User,
):
    investigation = get_investigation(db, investigation_id)

    if investigation is None:
        raise HTTPException(status_code=404, detail="Investigation not found")

    agent = db.query(User).filter(User.id == data.agent_id).first()

    if agent is None:
        raise HTTPException(status_code=404, detail="Agent not found")

    if agent.role != "agent":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Investigation can only be assigned to an agent",
        )

    try:
        return assign_investigation(
            db,
            investigation,
            agent,
            current_user,
            data.note,
        )
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(error),
        ) from error


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

    if report is None:
        raise HTTPException(status_code=404, detail="Report not found")

    return report


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
        return save_report_draft(db, investigation, current_user, data.content)
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
        return submit_report(db, investigation)
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
        return review_investigation_report(
            db,
            investigation,
            current_user,
            data.decision,
            comments,
        )
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

    if data.status is not None and not is_valid_status_transition(
        investigation.status,
        data.status,
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Invalid status transition: "
                f"{investigation.status} -> {data.status}"
            ),
        )

    if current_user.role == "agent" and data.status not in {
        None,
        "in_progress",
        "under_review",
    }:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Agents cannot perform this status transition",
        )

    return update_investigation(db, investigation, data)

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

    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only admins can delete investigations",
        )

    delete_investigation(db, investigation)

    return {
        "message": "Investigation deleted successfully"
    }