from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class InvestigationAssignment(Base):
    __tablename__ = "investigation_assignments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    investigation_id: Mapped[int] = mapped_column(
        ForeignKey("investigations.id"),
        index=True,
    )
    agent_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"),
        index=True,
    )
    assigned_by_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"),
        index=True,
    )
    note: Mapped[str | None] = mapped_column(String(500), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    assigned_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
    )
    unassigned_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
    )