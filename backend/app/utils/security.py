from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import jwt
from pwdlib import PasswordHash

from app.config.settings import (
    JWT_SECRET_KEY,
    JWT_ALGORITHM,
    ACCESS_TOKEN_EXPIRE_MINUTES,
)

password_hash = PasswordHash.recommended()


def hash_password(password: str) -> str:
    return password_hash.hash(password)

def verify_password(password: str, hashed_password: str) -> bool:
    return password_hash.verify(password, hashed_password)


def create_access_token(subject: str, session_id: UUID | str) -> str:
    if not JWT_SECRET_KEY:
        raise RuntimeError("JWT_SECRET_KEY is not configured")

    expires_at = datetime.now(timezone.utc) + timedelta(
        minutes=ACCESS_TOKEN_EXPIRE_MINUTES
    )
    issued_at = datetime.now(timezone.utc)

    payload = {
        "sub": subject,
        "sid": str(session_id),
        "iat": issued_at,
        "exp": expires_at,
        "typ": "access",
        "jti": uuid4().hex,
    }

    return jwt.encode(
        payload,
        JWT_SECRET_KEY,
        algorithm=JWT_ALGORITHM,
    )
