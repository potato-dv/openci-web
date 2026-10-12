from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.controllers.user import create, get_all, get_all_agents, get_one, login, update_activation, update_role
from app.database.session import get_db
from app.schemas.user import UserActivationUpdate, UserCreate, UserResponse, UserLogin, UserRoleUpdate
from app.models.user import User
from app.utils.auth import get_current_user, require_roles


router = APIRouter(
    prefix="/users",
    tags=["Users"],
)


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
    db: Session = Depends(get_db),
):
    return login(db, data)
