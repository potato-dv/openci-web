from datetime import date, datetime, timezone

from sqlalchemy import CheckConstraint, Date, DateTime, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class InvestigationRouteEvent(Base):
    """Audited attempts and unvisited carry-overs outside normal reports."""

    __tablename__ = "investigation_route_events"
    __table_args__ = (
        CheckConstraint(
            "event_type IN ('no_contact', 'shift_end_not_visited')",
            name="ck_route_events_type",
        ),
        CheckConstraint(
            "state IN ('deferred', 'retrying', 'retry_failed', 'carried_over', 'resolved')",
            name="ck_route_events_state",
        ),
        CheckConstraint("retry_number IN (0, 1)", name="ck_route_events_retry_number"),
        CheckConstraint(
            "(contact_available_from IS NULL AND contact_available_until IS NULL) OR "
            "(contact_available_until IS NULL OR contact_available_from IS NULL OR "
            "contact_available_until > contact_available_from)",
            name="ck_route_events_contact_window",
        ),
        UniqueConstraint(
            "investigation_id", "agent_id", "work_date", "retry_number",
            name="uq_route_event_investigation_agent_date_retry",
        ),
        Index("ix_route_events_agent_date_state", "agent_id", "work_date", "state"),
        Index("ix_route_events_investigation_attempted", "investigation_id", "attempted_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    investigation_id: Mapped[int] = mapped_column(
        ForeignKey("investigations.id", ondelete="CASCADE"), nullable=False, index=True,
    )
    agent_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True,
    )
    work_date: Mapped[date] = mapped_column(Date, nullable=False)
    planning_run_id: Mapped[int | None] = mapped_column(
        ForeignKey("planning_runs.id", ondelete="SET NULL"), nullable=True,
    )
    parent_event_id: Mapped[int | None] = mapped_column(
        ForeignKey("investigation_route_events.id", ondelete="SET NULL"), nullable=True,
    )
    event_type: Mapped[str] = mapped_column(String(32), nullable=False)
    state: Mapped[str] = mapped_column(String(24), nullable=False)
    retry_number: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default=text("0"))
    reason: Mapped[str] = mapped_column(String(80), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    contact_available_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    contact_available_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    attempted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc),
    )
    next_work_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    finalized_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
