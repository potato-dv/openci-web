from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.controllers.investigation import create, get_all, get_one, update, delete
from app.database.session import get_db
from app.schemas.investigation import InvestigationCreate, InvestigationUpdate

router = APIRouter(
    prefix="/investigations",
    tags=["Investigations"],
    )

@router.get("/")
def get_investigations(
    db: Session = Depends(get_db),
):  
    return get_all(db)

@router.post("/")
def create_investigation(
    data: InvestigationCreate,
    db: Session = Depends(get_db),
):
    return create(db, data)

@router.get("/{investigation_id}")
def get_investigation(
    investigation_id: int,
    db: Session = Depends(get_db),
):
    return get_one(db, investigation_id)

@router.patch("/{investigation_id}")
def update_investigation(
    investigation_id: int,
    data: InvestigationUpdate,
    db: Session = Depends(get_db),
):
    return update(db, investigation_id, data)

@router.delete("/{investigation_id}")
def delete_investigation(
    investigation_id: int,
    db: Session = Depends(get_db),
):
    return delete(db, investigation_id)