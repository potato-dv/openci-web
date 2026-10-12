from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session, joinedload

from app.controllers.investigation import (
    assign,
    create,
    delete,
    get_investigation_report,
    get_investigation_report_versions,
    get_one,
    review_report,
    save_investigation_report,
    submit_investigation_report,
    update,
)
from app.database.session import get_db
from app.models.assignment import InvestigationAssignment
from app.models.investigation import Investigation
from app.models.review import InvestigationReview
from app.models.user import User
from app.schemas.investigation import InvestigationCreate, InvestigationResponse, InvestigationUpdate
from app.schemas.assignment import AssignmentCreate, AssignmentResponse
from app.schemas.report import ReportResponse, ReportUpsert
from app.schemas.review import ReviewCreate, ReviewResponse
from app.utils.auth import get_current_user, require_roles

router = APIRouter(
    prefix="/investigations",
    tags=["Investigations"],
    )


@router.get(
    "/{investigation_id}/reviews",
    response_model=list[ReviewResponse],
)
def list_reviews_for_investigation(
    investigation_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    get_one(db, investigation_id, current_user)
    return (
        db.query(InvestigationReview)
        .options(joinedload(InvestigationReview.reviewer))
        .filter(InvestigationReview.investigation_id == investigation_id)
        .order_by(InvestigationReview.reviewed_at.desc())
        .all()
    )


@router.post(
    "/{investigation_id}/reviews",
    response_model=ReviewResponse,
)
def review_investigation(
    investigation_id: int,
    data: ReviewCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("admin", "supervisor")),
):
    return review_report(db, investigation_id, data, current_user)


@router.get(
    "/{investigation_id}/report",
    response_model=ReportResponse | None,
)
def get_report_for_investigation(
    investigation_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return get_investigation_report(db, investigation_id, current_user)


@router.get(
    "/{investigation_id}/reports",
    response_model=list[ReportResponse],
)
def list_report_versions_for_investigation(
    investigation_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return get_investigation_report_versions(db, investigation_id, current_user)


@router.put(
    "/{investigation_id}/report",
    response_model=ReportResponse,
)
def save_report_for_investigation(
    investigation_id: int,
    data: ReportUpsert,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return save_investigation_report(db, investigation_id, data, current_user)


@router.post(
    "/{investigation_id}/report/submit",
    response_model=ReportResponse,
)
def submit_report_for_investigation(
    investigation_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return submit_investigation_report(db, investigation_id, current_user)


@router.post(
    "/{investigation_id}/assign",
    response_model=AssignmentResponse,
)
def assign_investigation_to_agent(
    investigation_id: int,
    data: AssignmentCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("admin", "supervisor")),
):
    return assign(db, investigation_id, data, current_user)


@router.get(
    "/{investigation_id}/assignments",
    response_model=list[AssignmentResponse],
)
def list_investigation_assignments(
    investigation_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("admin", "supervisor")),
):
    get_one(db, investigation_id, current_user)
    return (
        db.query(InvestigationAssignment)
        .options(
            joinedload(InvestigationAssignment.agent),
            joinedload(InvestigationAssignment.assigned_by),
        )
        .filter_by(investigation_id=investigation_id)
        .order_by(InvestigationAssignment.assigned_at.desc())
        .all()
    )

@router.get("/", response_model=list[InvestigationResponse])
def get_investigations(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):  
    query = db.query(Investigation).options(joinedload(Investigation.assigned_agent))
    query = query.filter(Investigation.deleted_at.is_(None))
    if current_user.role == "agent":
        query = query.filter(Investigation.assigned_agent_id == current_user.id)
    return query.order_by(Investigation.created_at.desc()).all()

@router.post("/", response_model=InvestigationResponse)
def create_investigation(
    data: InvestigationCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("admin", "supervisor")),
):
    return create(db, data, current_user)

@router.get("/{investigation_id}", response_model=InvestigationResponse)
def get_investigation(
    investigation_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return get_one(db, investigation_id, current_user)

@router.patch("/{investigation_id}", response_model=InvestigationResponse)
def update_investigation(
    investigation_id: int,
    data: InvestigationUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return update(db, investigation_id, data, current_user)

@router.delete("/{investigation_id}")
def delete_investigation(
    investigation_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return delete(db, investigation_id, current_user)
