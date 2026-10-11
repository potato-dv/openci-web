from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.controllers.investigation import (
    assign,
    create,
    delete,
    get_all,
    get_assignments,
    get_investigation_report,
    get_reviews,
    get_one,
    review_report,
    save_investigation_report,
    submit_investigation_report,
    update,
)
from app.database.session import get_db
from app.models.user import User
from app.schemas.investigation import InvestigationCreate, InvestigationUpdate
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
    return get_reviews(db, investigation_id, current_user)


@router.post(
    "/{investigation_id}/reviews",
    response_model=ReviewResponse,
)
def review_investigation(
    investigation_id: int,
    data: ReviewCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("supervisor")),
):
    return review_report(db, investigation_id, data, current_user)


@router.get(
    "/{investigation_id}/report",
    response_model=ReportResponse,
)
def get_report_for_investigation(
    investigation_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return get_investigation_report(db, investigation_id, current_user)


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
    current_user: User = Depends(require_roles("supervisor")),
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
    return get_assignments(db, investigation_id)

@router.get("/")
def get_investigations(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):  
    return get_all(db, current_user)

@router.post("/")
def create_investigation(
    data: InvestigationCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("supervisor")),
):
    return create(db, data)

@router.get("/{investigation_id}")
def get_investigation(
    investigation_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return get_one(db, investigation_id, current_user)

@router.patch("/{investigation_id}")
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