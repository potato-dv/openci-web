from datetime import date, datetime, timezone

from sqlalchemy import CheckConstraint, Date, DateTime, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class AgentRevisitRequest(Base):
    __tablename__ = "agent_revisit_requests"
    __table_args__ = (
        CheckConstraint(
            "status IN ('waiting_for_shift', 'queued', 'routed', 'completed', 'cancelled')",
            name="ck_agent_revisit_requests_status",
        ),
        UniqueConstraint("report_id", name="uq_agent_revisit_requests_report"),
        Index("ix_agent_revisit_requests_agent_status_date", "agent_id", "status", "target_work_date"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    investigation_id: Mapped[int] = mapped_column(
        ForeignKey("investigations.id", ondelete="CASCADE"), nullable=False, index=True,
    )
    report_id: Mapped[int] = mapped_column(
        ForeignKey("investigation_reports.id", ondelete="CASCADE"), nullable=False, index=True,
    )
    agent_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    target_work_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="waiting_for_shift", server_default="waiting_for_shift")
    planning_run_id: Mapped[int | None] = mapped_column(ForeignKey("planning_runs.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
