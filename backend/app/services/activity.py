from sqlalchemy.orm import Session

from app.models.activity import ActivityLog
from app.models.user import User


def record_activity(
    db: Session,
    actor: User | None,
    action: str,
    object_type: str,
    object_id: int | None,
    details: dict | None = None,
) -> None:
    db.add(ActivityLog(
        actor_id=actor.id if actor else None,
        action=action,
        object_type=object_type,
        object_id=object_id,
        details=details or {},
    ))
    db.commit()
