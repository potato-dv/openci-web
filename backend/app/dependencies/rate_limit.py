from fastapi import Depends, Request, Response

from app.models.user import User
from app.services.rate_limit import GENERAL_POLICY, PLANNING_POLICY, WRITE_POLICY, enforce
from app.utils.auth import get_current_user


def general_api_rate_limit(
    request: Request,
    response: Response,
    user: User = Depends(get_current_user),
) -> None:
    identity = f"user:{user.id}"
    enforce(request, response, GENERAL_POLICY, identity)
    if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
        enforce(request, response, WRITE_POLICY, identity)


def planning_enqueue_rate_limit(
    request: Request,
    response: Response,
    user: User = Depends(get_current_user),
) -> None:
    enforce(request, response, PLANNING_POLICY, f"user:{user.id}")
