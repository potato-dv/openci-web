from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import secrets
from typing import NoReturn
from uuid import UUID, uuid4

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.config.settings import (
    AUTH_REFRESH_TOKEN_GRACE_SECONDS,
    AUTH_REFRESH_TOKEN_RETENTION_DAYS,
    AUTH_SESSION_ABSOLUTE_HOURS,
    AUTH_SESSION_IDLE_MINUTES,
)
from app.models.auth_session import AuthRefreshToken, AuthSession
from app.models.user import User
from app.utils.security import create_access_token


@dataclass(frozen=True)
class IssuedSession:
    access_token: str
    refresh_cookie: str
    refresh_max_age: int


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _auth_error(
    code: str,
    message: str,
    status_code: int = status.HTTP_401_UNAUTHORIZED,
) -> NoReturn:
    headers = {"WWW-Authenticate": "Bearer"} if status_code == status.HTTP_401_UNAUTHORIZED else None
    raise HTTPException(
        status_code=status_code,
        detail={"code": code, "message": message},
        headers=headers,
    )


def _new_refresh_value(session_id: UUID) -> str:
    return f"{session_id}.{secrets.token_urlsafe(32)}"


def issue_session(db: Session, user: User) -> IssuedSession:
    now = utc_now()
    session_id = uuid4()
    expires_at = now + timedelta(hours=AUTH_SESSION_ABSOLUTE_HOURS)
    session = AuthSession(
        id=session_id,
        user_id=user.id,
        created_at=now,
        absolute_expires_at=expires_at,
        last_interactive_at=now,
    )
    refresh_value = _new_refresh_value(session_id)
    db.add(session)
    db.flush()
    db.add(
        AuthRefreshToken(
            session_id=session_id,
            token_hash=_token_hash(refresh_value),
            generation=0,
            issued_at=now,
        )
    )
    access_token = create_access_token(str(user.id), session_id)
    db.commit()
    return IssuedSession(
        access_token=access_token,
        refresh_cookie=refresh_value,
        refresh_max_age=max(0, int((expires_at - now).total_seconds())),
    )


def parse_session_id(refresh_value: str | None) -> UUID | None:
    if not refresh_value or len(refresh_value) > 256:
        return None
    session_part, separator, secret_part = refresh_value.partition(".")
    if not separator or not secret_part:
        return None
    try:
        return UUID(session_part)
    except (ValueError, AttributeError):
        return None


def rotate_refresh_token(db: Session, refresh_value: str | None) -> IssuedSession:
    session_id = parse_session_id(refresh_value)
    if session_id is None or refresh_value is None:
        _auth_error("session_missing", "Sign in to continue.")

    # On PostgreSQL this serializes refresh requests for one browser session.
    session = (
        db.query(AuthSession)
        .filter(AuthSession.id == session_id)
        .with_for_update()
        .first()
    )
    if session is None or session.revoked_at is not None:
        _auth_error("session_revoked", "This session has ended. Sign in again.")

    now = utc_now()
    absolute_expiry = _aware(session.absolute_expires_at)
    last_interactive = _aware(session.last_interactive_at)
    if now >= absolute_expiry:
        session.revoked_at = now
        session.revoke_reason = "absolute_expired"
        db.commit()
        _auth_error("session_expired", "Your session reached its maximum duration. Sign in again.")
    if now - last_interactive >= timedelta(minutes=AUTH_SESSION_IDLE_MINUTES):
        session.revoked_at = now
        session.revoke_reason = "idle_expired"
        db.commit()
        _auth_error("session_idle", "You were signed out after being inactive. Sign in again.")

    token = (
        db.query(AuthRefreshToken)
        .filter(
            AuthRefreshToken.session_id == session_id,
            AuthRefreshToken.token_hash == _token_hash(refresh_value),
        )
        .first()
    )
    if token is None:
        _auth_error("session_revoked", "This refresh session is no longer valid.")

    if token.used_at is not None:
        used_at = _aware(token.used_at)
        if now - used_at <= timedelta(seconds=AUTH_REFRESH_TOKEN_GRACE_SECONDS):
            _auth_error(
                "refresh_conflict",
                "Another tab refreshed this session at the same time. Retry the request.",
                status.HTTP_409_CONFLICT,
            )
        session.revoked_at = now
        session.revoke_reason = "refresh_reuse"
        db.commit()
        _auth_error("session_revoked", "Refresh token reuse was detected. Sign in again.")

    token.used_at = now
    next_value = _new_refresh_value(session_id)
    next_token = AuthRefreshToken(
        session_id=session_id,
        token_hash=_token_hash(next_value),
        generation=token.generation + 1,
        issued_at=now,
    )
    db.add(next_token)
    db.flush()

    user = db.query(User).filter(User.id == session.user_id).first()
    if user is None or not user.is_active:
        session.revoked_at = now
        session.revoke_reason = "account_changed"
        db.commit()
        _auth_error("session_revoked", "This account is no longer active. Sign in again.")

    access_token = create_access_token(str(user.id), session_id)
    db.commit()
    return IssuedSession(
        access_token=access_token,
        refresh_cookie=next_value,
        refresh_max_age=max(0, int((absolute_expiry - now).total_seconds())),
    )


def revoke_session(db: Session, session_id: UUID | None, reason: str = "logout") -> None:
    if session_id is None:
        return
    session = db.query(AuthSession).filter(AuthSession.id == session_id).with_for_update().first()
    if session is not None and session.revoked_at is None:
        session.revoked_at = utc_now()
        session.revoke_reason = reason
        db.commit()


def revoke_user_sessions(db: Session, user_id: int, reason: str = "account_changed") -> None:
    now = utc_now()
    db.query(AuthSession).filter(
        AuthSession.user_id == user_id,
        AuthSession.revoked_at.is_(None),
    ).update(
        {AuthSession.revoked_at: now, AuthSession.revoke_reason: reason},
        synchronize_session=False,
    )


def record_interactive_activity(db: Session, session_id: UUID) -> None:
    session = db.query(AuthSession).filter(AuthSession.id == session_id).first()
    if session is not None and session.revoked_at is None:
        session.last_interactive_at = utc_now()
        db.commit()


def prune_old_auth_sessions(db: Session) -> int:
    cutoff = utc_now() - timedelta(days=AUTH_REFRESH_TOKEN_RETENTION_DAYS)
    deleted = db.query(AuthSession).filter(
        AuthSession.absolute_expires_at < cutoff,
    ).delete(synchronize_session=False)
    db.commit()
    return deleted
