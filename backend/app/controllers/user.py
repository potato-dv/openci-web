from fastapi import HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from app.schemas.user import UserCreate, UserLogin
from app.models.user import User
from app.models.assignment import InvestigationAssignment
from app.models.investigation import Investigation
from app.services.user import (
    create_user,
    get_agents,
    get_users,
    get_user_by_email,
    get_user_by_id,
    authenticate_user,
    set_user_active,
    set_user_role,
)

from app.utils.security import create_access_token

def create(db: Session, data: UserCreate, actor: User):
    existing_user = get_user_by_email(db, data.email)

    if existing_user:
        raise HTTPException(
            status_code=409,
            detail="Email is already registered",
        )

    try:
        user = create_user(db, data)
    except IntegrityError as error:
        db.rollback()
        raise HTTPException(status_code=409, detail="Email is already registered") from error
    from app.services.activity import record_activity

    record_activity(db, actor, "user.created", "user", user.id, {"role": user.role})
    return user


def get_all(db: Session):
    return get_users(db)


def get_all_agents(db: Session):
    return get_agents(db)

def get_one(db: Session, user_id: int):
    user = get_user_by_id(db, user_id)

    if user is None:
        raise HTTPException(
            status_code=404,
            detail="User not found",
        )

    return user


def update_activation(db: Session, user_id: int, is_active: bool, actor: User):
    user = get_user_by_id(db, user_id)

    if user is None:
        raise HTTPException(status_code=404, detail="User not found")

    if user.id == actor.id and not is_active:
        raise HTTPException(
            status_code=400,
            detail="You cannot deactivate your own account",
        )

    if user.role == "agent" and user.is_active and not is_active:
        active_assignments = db.query(InvestigationAssignment).join(
            Investigation,
            Investigation.id == InvestigationAssignment.investigation_id,
        ).filter(
            InvestigationAssignment.agent_id == user.id,
            InvestigationAssignment.is_active.is_(True),
            Investigation.status != "completed",
            Investigation.deleted_at.is_(None),
        ).count()
        if active_assignments:
            raise HTTPException(status_code=409, detail="Reassign this agent’s active investigations before deactivation")

    if user.role == "admin" and user.is_active and not is_active:
        active_admins = db.query(User).filter(User.role == "admin", User.is_active.is_(True)).count()
        if active_admins <= 1:
            raise HTTPException(status_code=409, detail="At least one active admin account must remain")

    updated = set_user_active(db, user, is_active)
    from app.services.activity import record_activity

    record_activity(db, actor, "user.activation_changed", "user", user.id, {"is_active": is_active})
    return updated


def update_role(db: Session, user_id: int, role: str, actor: User):
    user = get_user_by_id(db, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    if user.role == "admin" and user.is_active and role != "admin":
        active_admins = db.query(User).filter(User.role == "admin", User.is_active.is_(True)).count()
        if active_admins <= 1:
            raise HTTPException(status_code=409, detail="At least one active admin account must remain")
    if user.role == "agent" and role != "agent":
        active_assignments = db.query(InvestigationAssignment).join(
            Investigation,
            Investigation.id == InvestigationAssignment.investigation_id,
        ).filter(
            InvestigationAssignment.agent_id == user.id,
            InvestigationAssignment.is_active.is_(True),
            Investigation.status != "completed",
            Investigation.deleted_at.is_(None),
        ).count()
        if active_assignments:
            raise HTTPException(status_code=409, detail="Reassign this agent’s active investigations before changing their role")
    previous_role = user.role
    updated = set_user_role(db, user, role)
    from app.services.activity import record_activity

    record_activity(db, actor, "user.role_changed", "user", user.id, {"from": previous_role, "to": role})
    return updated

def login(db: Session, data: UserLogin):
    user = authenticate_user(
        db=db,
        email=data.email,
        password=data.password,
    )

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    access_token = create_access_token(subject=str(user.id))

    return {
        "access_token": access_token,
        "token_type": "bearer",
    }
