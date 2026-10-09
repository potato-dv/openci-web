from app.workers.celery_app import celery_app
from app.database import SessionLocal
from app.models.investigation import Investigation


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
            .filter(Investigation.id == investigation_id)
            .first()
        )

        if investigation is None:
            return {
                "status": "failed",
                "message": "Investigation not found",
            }

        investigation.status = "processing"

        db.commit()
        db.refresh(investigation)

        print(f"Processing investigation {investigation.id}")

        return {
            "investigation_id": investigation.id,
            "status": "processing",
        }

    finally:
        db.close()