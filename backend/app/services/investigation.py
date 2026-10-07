from sqlalchemy.orm import Session

from app.models.investigation import Investigation
from app.schemas.investigation import InvestigationCreate, InvestigationUpdate


def create_investigation(
    db: Session,
    data: InvestigationCreate,
) -> Investigation:
    investigation = Investigation(
        reference_number=data.reference_number,
        subject_name=data.subject_name,
        address=data.address,
        status=data.status,
        priority=data.priority,
    )

    db.add(investigation)
    db.commit()
    db.refresh(investigation)

    return investigation

def get_investigations(db: Session) -> list[Investigation]:
    return db.query(Investigation).all()

def get_investigation(
    db: Session,
    investigation_id: int,
) -> Investigation | None:
    return (
        db.query(Investigation)
        .filter(Investigation.id == investigation_id)
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

def delete_investigation(
    db: Session,
    investigation: Investigation,
) -> None:
    db.delete(investigation)
    db.commit()