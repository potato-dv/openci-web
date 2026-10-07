from sqlalchemy.orm import Session

from app.schemas.investigation import InvestigationCreate, InvestigationUpdate
from app.services.investigation import ( 
    create_investigation,
    delete_investigation,
    get_investigations,
    get_investigation,
    update_investigation,
    )

from fastapi import HTTPException

def create(
    db: Session,
    data: InvestigationCreate,
):
    return create_investigation(db, data)

def get_all(db: Session):
    return get_investigations(db)

def get_one(
    db: Session,
    investigation_id: int,
):
    investigation = get_investigation(db, investigation_id)

    if investigation is None:
        raise HTTPException(
            status_code=404,
            detail="Investigation not found",
        )

    return investigation

def update(
    db: Session,
    investigation_id: int,
    data: InvestigationUpdate,
):
    investigation = get_investigation(db, investigation_id)

    if investigation is None:
        raise HTTPException(
            status_code=404,
            detail="Investigation not found",
        )

    return update_investigation(db, investigation, data)

def delete(
    db: Session,
    investigation_id: int,
):
    investigation = get_investigation(db, investigation_id)

    if investigation is None:
        raise HTTPException(
            status_code=404,
            detail="Investigation not found",
        )

    delete_investigation(db, investigation)

    return {
        "message": "Investigation deleted successfully"
    }