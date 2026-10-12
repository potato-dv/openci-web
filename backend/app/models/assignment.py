from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.investigation import Investigation
    from app.models.user import User


class InvestigationAssignment(Base):
    __tablename__ = "investigation_assignments"
    __table_args__ = (
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
    note: Mapped[str | None] = mapped_column(String(500), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    assigned_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    unassigned_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
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
