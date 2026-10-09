from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.schemas.user import UserCreate, UserLogin
from app.services.user import (
    create_user,
    get_users,
    get_user_by_email,
    get_user_by_id,
    authenticate_user,
)

from app.utils.security import create_access_token

def create(db: Session, data: UserCreate):
    existing_user = get_user_by_email(db, data.email)

    if existing_user:
        raise HTTPException(
            status_code=409,
            detail="Email is already registered",
        )

    return create_user(db, data)


def get_all(db: Session):
    return get_users(db)

def get_one(db: Session, user_id: int):
    user = get_user_by_id(db, user_id)

    if user is None:
        raise HTTPException(
            status_code=404,
            detail="User not found",
        )

    return user

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