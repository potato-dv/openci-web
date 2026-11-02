from datetime import datetime
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, String, Uuid, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class AuthSession(Base):
    __tablename__ = "auth_sessions"
    __table_args__ = (
        CheckConstraint(
            "revoke_reason IS NULL OR revoke_reason IN ('logout', 'refresh_reuse', 'idle_expired', 'absolute_expired', 'account_changed')",
            name="ck_auth_sessions_revoke_reason",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    absolute_expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_interactive_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoke_reason: Mapped[str | None] = mapped_column(String(32))

    refresh_tokens: Mapped[list["AuthRefreshToken"]] = relationship(
        back_populates="session", cascade="all, delete-orphan"
    )


class AuthRefreshToken(Base):
    __tablename__ = "auth_refresh_tokens"
    __table_args__ = (
        UniqueConstraint("session_id", "generation", name="uq_auth_refresh_tokens_session_generation"),
        CheckConstraint("generation >= 0", name="ck_auth_refresh_tokens_generation_nonnegative"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    session_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("auth_sessions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    generation: Mapped[int] = mapped_column(Integer, nullable=False)
    issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    session: Mapped[AuthSession] = relationship(back_populates="refresh_tokens")
