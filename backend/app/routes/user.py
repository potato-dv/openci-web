from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

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
