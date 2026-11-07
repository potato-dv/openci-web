from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError

from app.config.settings import AUTH_REFRESH_COOKIE_SAMESITE, AUTH_REFRESH_COOKIE_SECURE
from app.controllers.user import (
    create,
    get_all,
    get_all_agents,
    get_one,
    login,
    update_activation,
    update_role,
)
from app.database.session import get_db
from app.schemas.user import UserActivationUpdate, UserCreate, UserResponse, UserLogin, UserRoleUpdate
from app.models.user import User
from app.models.activity import ActivityLog
from app.models.user_permission_override import UserPermissionOverride
from app.schemas.agent_permissions import AgentPermissionHistoryResponse, AgentPermissionOverrideMap, AgentPermissionState
from app.services.agent_permissions import FEATURES_BY_CODE, effective_agent_permissions, permission_state
from app.services.auth_sessions import (
    parse_session_id,
    record_interactive_activity,
    revoke_session,
    rotate_refresh_token,
)
from app.utils.auth import (
    AuthContext,
    get_current_auth_context,
    get_current_user,
    require_browser_csrf,
    require_roles,
)


router = APIRouter(
    prefix="/users",
    tags=["Users"],
)

REFRESH_COOKIE_NAME = (
    "__Secure-openci_refresh" if AUTH_REFRESH_COOKIE_SECURE else "openci_refresh"
)
REFRESH_COOKIE_PATH = "/users"


def _set_refresh_cookie(response: Response, token: str, max_age: int) -> None:
    response.set_cookie(
        key=REFRESH_COOKIE_NAME,
        value=token,
        max_age=max_age,
        path=REFRESH_COOKIE_PATH,
        secure=AUTH_REFRESH_COOKIE_SECURE,
        httponly=True,
        samesite=AUTH_REFRESH_COOKIE_SAMESITE,
    )


def _clear_refresh_cookie(response: Response) -> None:
    response.delete_cookie(
        key=REFRESH_COOKIE_NAME,
        path=REFRESH_COOKIE_PATH,
        secure=AUTH_REFRESH_COOKIE_SECURE,
        httponly=True,
        samesite=AUTH_REFRESH_COOKIE_SAMESITE,
    )


def _mark_auth_response_private(response: Response) -> None:
    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"


# Admin only: Create a user
@router.post(
    "/",
    response_model=UserResponse,
    dependencies=[Depends(require_roles("admin"))],
)
def create_user(
    data: UserCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("admin")),
):
    return create(db, data, current_user)


# Authenticated users: View their own profile
@router.get("/me", response_model=UserResponse)
def get_current_user_profile(
    current_user: User = Depends(get_current_user),
):
    return current_user


# Admin only: List all users
@router.get(
    "/",
    response_model=list[UserResponse],
    dependencies=[Depends(require_roles("admin"))],
)
def get_users(
    db: Session = Depends(get_db),
):
    return get_all(db)


@router.get(
    "/agents",
    response_model=list[UserResponse],
    dependencies=[Depends(require_roles("admin", "supervisor"))],
)
def get_agents(
    db: Session = Depends(get_db),
):
    return get_all_agents(db)


@router.get("/me/agent-permissions")
def get_my_agent_permissions(
    response: Response,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role != "agent":
        raise HTTPException(status_code=403, detail="Agent permissions are available only to Agents")
    response.headers["Cache-Control"] = "private, no-store"
    return {"permissions": effective_agent_permissions(db, current_user)}


def _get_agent_for_permissions(db: Session, agent_id: int) -> User:
    agent = db.query(User).filter(User.id == agent_id, User.role == "agent").first()
    if agent is None:
        raise HTTPException(status_code=404, detail="Agent not found")
    return agent


@router.get("/{agent_id}/agent-permissions", response_model=AgentPermissionState)
def get_agent_permissions(
    agent_id: int,
    response: Response,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles("admin")),
):
    response.headers["Cache-Control"] = "private, no-store"
    return permission_state(db, _get_agent_for_permissions(db, agent_id))


@router.put("/{agent_id}/agent-permissions", response_model=AgentPermissionState)
def set_agent_permissions(
    agent_id: int,
    data: AgentPermissionOverrideMap,
    response: Response,
    db: Session = Depends(get_db),
    actor: User = Depends(require_roles("admin")),
):
    agent = _get_agent_for_permissions(db, agent_id)
    rows = db.query(UserPermissionOverride).filter(
        UserPermissionOverride.user_id == agent.id,
    ).with_for_update().all()
    old_overrides = {code: "inherit" for code in FEATURES_BY_CODE}
    old_overrides.update({row.feature_code: row.effect for row in rows})
    old_effective = {
        code: (old_overrides[code] == "allow" if old_overrides[code] != "inherit" else FEATURES_BY_CODE[code]["default_allowed"])
        for code in FEATURES_BY_CODE
    }
    row_by_code = {row.feature_code: row for row in rows}
    new_overrides = dict(data.overrides)
    for code, effect in new_overrides.items():
        row = row_by_code.get(code)
        if effect == "inherit":
            if row is not None:
                db.delete(row)
        elif row is None:
            db.add(UserPermissionOverride(user_id=agent.id, feature_code=code, effect=effect))
        else:
            row.effect = effect
    new_effective = {
        code: (new_overrides[code] == "allow" if new_overrides[code] != "inherit" else FEATURES_BY_CODE[code]["default_allowed"])
        for code in FEATURES_BY_CODE
    }
    if old_overrides != new_overrides or old_effective != new_effective:
        db.add(ActivityLog(
            actor_id=actor.id,
            action="agent.permissions_changed",
            object_type="user",
            object_id=agent.id,
            details={
                "old_overrides": old_overrides,
                "new_overrides": new_overrides,
                "old_effective": old_effective,
                "new_effective": new_effective,
            },
        ))
    try:
        db.commit()
    except IntegrityError as error:
        db.rollback()
        raise HTTPException(status_code=409, detail="Agent permissions changed concurrently; reload and try again") from error
    response.headers["Cache-Control"] = "private, no-store"
    return permission_state(db, agent)


@router.get("/{agent_id}/agent-permissions/history", response_model=AgentPermissionHistoryResponse)
def get_agent_permission_history(
    agent_id: int,
    response: Response,
    limit: int = Query(default=25, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    _: User = Depends(require_roles("admin")),
):
    agent = _get_agent_for_permissions(db, agent_id)
    query = db.query(ActivityLog).filter(
        ActivityLog.action == "agent.permissions_changed",
        ActivityLog.object_type == "user",
        ActivityLog.object_id == agent.id,
    )
    total = query.with_entities(func.count(ActivityLog.id)).scalar() or 0
    rows = query.order_by(ActivityLog.created_at.desc(), ActivityLog.id.desc()).offset(offset).limit(limit).all()
    response.headers["Cache-Control"] = "private, no-store"
    return {
        "items": [
            {
                "id": row.id,
                "actor_name": row.actor.name if row.actor else None,
                "created_at": row.created_at,
                "old_overrides": row.details.get("old_overrides", {}),
                "new_overrides": row.details.get("new_overrides", {}),
                "old_effective": row.details.get("old_effective", {}),
                "new_effective": row.details.get("new_effective", {}),
            }
            for row in rows
        ],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


# Admin only: Get a specific user
@router.get(
    "/{user_id}",
    response_model=UserResponse,
    dependencies=[Depends(require_roles("admin"))],
)
def get_user(
    user_id: int,
    db: Session = Depends(get_db),
):
    return get_one(db, user_id)


# Admin only: Activate or deactivate a user
@router.patch(
    "/{user_id}/activation",
    response_model=UserResponse,
    dependencies=[Depends(require_roles("admin"))],
)
def set_user_activation(
    user_id: int,
    data: UserActivationUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("admin")),
):
    return update_activation(db, user_id, data.is_active, current_user)


@router.patch(
    "/{user_id}/role",
    response_model=UserResponse,
    dependencies=[Depends(require_roles("admin"))],
)
def set_user_role(
    user_id: int,
    data: UserRoleUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("admin")),
):
    return update_role(db, user_id, data.role, current_user)


# Public: Login
@router.post("/login")
def login_user(
    data: UserLogin,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
):
    require_browser_csrf(request)
    issued = login(db, data)
    _set_refresh_cookie(response, issued.refresh_cookie, issued.refresh_max_age)
    _mark_auth_response_private(response)
    return {"access_token": issued.access_token, "token_type": "bearer"}


@router.post("/refresh")
def refresh_user_session(
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
):
    require_browser_csrf(request)
    try:
        issued = rotate_refresh_token(db, request.cookies.get(REFRESH_COOKIE_NAME))
    except HTTPException as error:
        if error.status_code == status.HTTP_401_UNAUTHORIZED:
            _clear_refresh_cookie(response)
            headers = dict(response.headers)
            headers["Cache-Control"] = "no-store"
            headers["Pragma"] = "no-cache"
            headers.update(error.headers or {})
            return JSONResponse(
                status_code=error.status_code,
                content={"detail": error.detail},
                headers=headers,
            )
        raise
    _set_refresh_cookie(response, issued.refresh_cookie, issued.refresh_max_age)
    _mark_auth_response_private(response)
    return {"access_token": issued.access_token, "token_type": "bearer"}


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout_user(
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
):
    require_browser_csrf(request)
    revoke_session(db, parse_session_id(request.cookies.get(REFRESH_COOKIE_NAME)))
    _clear_refresh_cookie(response)
    response.status_code = status.HTTP_204_NO_CONTENT
    return response


@router.post("/activity", status_code=status.HTTP_204_NO_CONTENT)
def record_user_activity(
    response: Response,
    context: AuthContext = Depends(get_current_auth_context),
    db: Session = Depends(get_db),
):
    record_interactive_activity(db, context.session.id)
    response.status_code = status.HTTP_204_NO_CONTENT
    return response
