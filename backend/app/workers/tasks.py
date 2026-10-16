from app.workers.celery_app import celery_app
from app.database import SessionLocal
from app.models.investigation import Investigation
from app.services.investigation import is_valid_status_transition


@celery_app.task(
    autoretry_for=(Exception,),
    retry_backoff=True,
    max_retries=3,
)
def process_investigation(investigation_id: int):
    db = SessionLocal()

    try:
        investigation = (
            db.query(Investigation)
            .filter(
                Investigation.id == investigation_id,
                Investigation.deleted_at.is_(None),
            )
            .with_for_update()
            .first()
        )

        if investigation is None:
            return {
                "status": "skipped",
                "message": "Investigation not found or deleted",
            }

        if investigation.status == "in_progress":
            return {
                "investigation_id": investigation.id,
                "status": investigation.status,
            }

        if not is_valid_status_transition(investigation.status, "in_progress"):
            return {
                "status": "failed",
                "message": f"Investigation cannot move from {investigation.status} to in_progress",
            }

        investigation.status = "in_progress"

        db.commit()
        db.refresh(investigation)

        print(f"Processing investigation {investigation.id}")

        return {
            "investigation_id": investigation.id,
            "status": "in_progress",
        }

    finally:
        db.close()
