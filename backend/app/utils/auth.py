import hmac
from dataclasses import dataclass
from datetime import timedelta
from urllib.parse import urlsplit
from uuid import UUID

import jwt

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from jwt.exceptions import ExpiredSignatureError, InvalidTokenError
from sqlalchemy.orm import Session

from app.config.settings import (
    AUTH_SESSION_IDLE_MINUTES,
    CORS_ALLOWED_ORIGINS,
    JWT_ALGORITHM,
    JWT_SECRET_KEY,
)
from app.database.session import get_db
from app.models.auth_session import AuthSession
from app.models.user import User
from app.services.user import get_user_by_id
from app.services.auth_sessions import _aware, utc_now


oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl="/users/login"
)


@dataclass(frozen=True)
class AuthContext:
    user: User
    session: AuthSession


def _auth_error(code: str, message: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail={"code": code, "message": message},
        headers={"WWW-Authenticate": "Bearer"},
    )


def get_current_auth_context(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> AuthContext:
    invalid_error = _auth_error("session_revoked", "Invalid or expired session. Sign in again.")

    try:
        payload = jwt.decode(
            token,
            JWT_SECRET_KEY,
            algorithms=[JWT_ALGORITHM],
            options={"require": ["sub", "sid", "iat", "exp", "typ", "jti"]},
        )

        subject = payload.get("sub")
        if subject is None or payload.get("typ") != "access":
            raise InvalidTokenError("Invalid token type")
        user_id = int(subject)
        session_id = UUID(str(payload.get("sid")))
    except ExpiredSignatureError:
        raise _auth_error("access_token_expired", "The access token expired.")
    except (InvalidTokenError, ValueError, TypeError, AttributeError):
        raise invalid_error

    auth_session = db.query(AuthSession).filter(AuthSession.id == session_id).first()
    if (
        auth_session is None
        or auth_session.user_id != user_id
        or auth_session.revoked_at is not None
    ):
        raise invalid_error

    now = utc_now()
    if now >= _aware(auth_session.absolute_expires_at):
        auth_session.revoked_at = now
        auth_session.revoke_reason = "absolute_expired"
        db.commit()
        raise _auth_error(
            "session_expired",
            "Your session reached its maximum duration. Sign in again.",
        )
    if now - _aware(auth_session.last_interactive_at) >= timedelta(minutes=AUTH_SESSION_IDLE_MINUTES):
        auth_session.revoked_at = now
        auth_session.revoke_reason = "idle_expired"
        db.commit()
        raise _auth_error(
            "session_idle",
            "You were signed out after being inactive. Sign in again.",
        )

    user = get_user_by_id(db, user_id)

    if user is None:
        raise invalid_error

    if not user.is_active:
        raise invalid_error

    return AuthContext(user=user, session=auth_session)


def get_current_user(
    context: AuthContext = Depends(get_current_auth_context),
) -> User:
    return context.user


def _origin_tuple(value: str) -> tuple[str, str, int | None] | None:
    try:
        parsed = urlsplit(value)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            return None
        if (
            parsed.username
            or parsed.password
            or parsed.path not in {"", "/"}
            or parsed.query
            or parsed.fragment
        ):
            return None
        port = parsed.port
        if port == (443 if parsed.scheme == "https" else 80):
            port = None
        return parsed.scheme.lower(), parsed.hostname.lower(), port
    except ValueError:
        return None


_allowed_origins = {
    origin
    for origin in (_origin_tuple(value) for value in CORS_ALLOWED_ORIGINS)
    if origin is not None
}


def is_allowed_websocket_origin(origin: str | None) -> bool:
    """Require browser WebSocket upgrades to come from a configured web origin."""
    return origin is not None and _origin_tuple(origin) in _allowed_origins


def require_browser_csrf(request: Request) -> None:
    csrf_header = request.headers.get("X-CSRF-Token", "")
    if not hmac.compare_digest(csrf_header, "1"):
        raise HTTPException(
            status_code=403,
            detail="A valid CSRF request header is required",
        )

    origin = request.headers.get("Origin")
    if origin is None:
        referer = request.headers.get("Referer")
        if referer:
            parsed = urlsplit(referer)
            origin = f"{parsed.scheme}://{parsed.netloc}"

    if origin is None or _origin_tuple(origin) not in _allowed_origins:
        raise HTTPException(
            status_code=403,
            detail="The request origin is not allowed",
        )


def require_roles(*allowed_roles: str):
    def role_checker(
        current_user: User = Depends(get_current_user),
    ) -> User:
        if current_user.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to perform this action",
            )

        return current_user

    return role_checker
