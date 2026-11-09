from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy import DateTime, Index, Integer, JSON, String, Uuid, text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class RealtimeOutboxEvent(Base):
    """Committed, content-free notification metadata awaiting Redis delivery."""

    __tablename__ = "realtime_outbox_events"
    __table_args__ = (
        Index("ix_realtime_outbox_pending", "published_at", "available_at", "id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    event_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), unique=True, default=uuid4, nullable=False)
    event_type: Mapped[str] = mapped_column(String(80), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(40), nullable=False)
    entity_id: Mapped[str] = mapped_column(String(80), nullable=False)
    investigation_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    recipient_user_ids: Mapped[list[int]] = mapped_column(JSON, nullable=False, default=list)
    recipient_roles: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc),
    )
    available_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc),
    )
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default=text("0"))
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str | None] = mapped_column(String(80), nullable=True)
