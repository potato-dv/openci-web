from fastapi import HTTPException, status

from app.config.settings import PLANNING_ENABLED


def require_planning_enabled() -> None:
    if not PLANNING_ENABLED:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Assignment planning is disabled",
        )
