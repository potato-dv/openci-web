from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session, joinedload

from app.database.session import get_db
from app.models.activity import ActivityLog
from app.models.user import User
from app.schemas.activity import ActivityLogResponse
from app.utils.auth import require_roles

router = APIRouter(prefix="/activity-logs", tags=["Activity"])


@router.get("/", response_model=list[ActivityLogResponse])
def list_activity_logs(
    db: Session = Depends(get_db),
    _: User = Depends(require_roles("admin")),
):
    return (
        db.query(ActivityLog)
        .options(joinedload(ActivityLog.actor))
        .order_by(ActivityLog.created_at.desc())
        .limit(250)
        .all()
    )
