from sqlalchemy.orm import Session

from app.models.user import User
from app.schemas.user import UserCreate

from app.utils.security import ( 
    hash_password, 
    verify_password,
)

def create_user(
    db: Session,
    data: UserCreate,
) -> User:
    user = User(
        name=data.name,
        email=data.email,
        password=hash_password(data.password),
        role=data.role,
    )

    db.add(user)
    db.commit()
    db.refresh(user)

    return user

def get_users(db: Session) -> list[User]:
    return db.query(User).all()


def get_agents(db: Session) -> list[User]:
    return db.query(User).filter(User.role == "agent", User.is_active.is_(True)).order_by(User.name).all()

def get_user_by_email(db: Session, email: str) -> User | None:
    return db.query(User).filter(User.email == email).first()

def get_user_by_id(db: Session, user_id: int) -> User | None:
    return db.query(User).filter(User.id == user_id).first()


def set_user_active(db: Session, user: User, is_active: bool) -> User:
    user.is_active = is_active
    db.commit()
    db.refresh(user)
    return user


def set_user_role(db: Session, user: User, role: str) -> User:
    user.role = role
    db.commit()
    db.refresh(user)
    return user

def authenticate_user(
    db: Session,
    email: str,
    password: str,
) -> User | None:
    user = get_user_by_email(db, email)

    if user is None:
        return None

    if not user.is_active:
        return None

    if not verify_password(password, user.password):
        return None

    return user
