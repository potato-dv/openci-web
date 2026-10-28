from datetime import date, datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, CheckConstraint, Date, DateTime, ForeignKey, Index, Integer, JSON, String, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.investigation import Investigation
    from app.models.user import User


class InvestigationAssignment(Base):
    __tablename__ = "investigation_assignments"
    __table_args__ = (
        CheckConstraint(
            "assignment_source IN ('manual', 'automatic')",
            name="ck_investigation_assignments_source",
        ),
        Index(
            "uq_assignment_active_per_investigation",
            "investigation_id",
            unique=True,
            postgresql_where=text("is_active IS TRUE"),
            sqlite_where=text("is_active IS 1"),
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    investigation_id: Mapped[int] = mapped_column(
        ForeignKey("investigations.id", ondelete="CASCADE"),
        index=True,
    )
    agent_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"),
        index=True,
    )
    assigned_by_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"),
        index=True,
    )
    assignment_source: Mapped[str] = mapped_column(String(20), nullable=False, default="manual", server_default=text("'manual'"))
    note: Mapped[str | None] = mapped_column(String(500), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    assigned_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    unassigned_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    auto_route_status: Mapped[str | None] = mapped_column(String(24), nullable=True)
    auto_route_work_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    auto_route_agent_ids: Mapped[list[int] | None] = mapped_column(JSON, nullable=True)
    auto_route_run_ids: Mapped[list[int] | None] = mapped_column(JSON, nullable=True)
    auto_route_errors: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    investigation: Mapped["Investigation"] = relationship(back_populates="assignments")
    agent: Mapped["User"] = relationship(
        foreign_keys=[agent_id], back_populates="assignments_as_agent"
    )
    assigned_by: Mapped["User"] = relationship(
        foreign_keys=[assigned_by_id], back_populates="assignments_created"
    )

    @property
    def agent_name(self) -> str:
        return self.agent.name

    @property
    def assigned_by_name(self) -> str:
        return self.assigned_by.name

    @property
    def route_refresh(self) -> dict | None:
        if self.auto_route_status is None:
            return None
        return {
            "status": self.auto_route_status,
            "work_date": self.auto_route_work_date,
            "agent_ids": self.auto_route_agent_ids or [],
            "run_ids": self.auto_route_run_ids or [],
            "errors": self.auto_route_errors or [],
        }
