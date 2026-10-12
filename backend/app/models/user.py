from typing import TYPE_CHECKING

from sqlalchemy import Boolean, CheckConstraint, Integer, String, true
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.assignment import InvestigationAssignment
    from app.models.investigation import Investigation
    from app.models.report import InvestigationReport
    from app.models.review import InvestigationReview


class User(Base):
    __tablename__ = "users"
    __table_args__ = (CheckConstraint("role IN ('admin', 'supervisor', 'agent')", name="ck_users_role"),)

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        index=True,
    )

    name: Mapped[str] = mapped_column(String(255))

    email: Mapped[str] = mapped_column(
        String(255),
        unique=True,
        index=True,
    )

    password: Mapped[str] = mapped_column(String(255))

    role: Mapped[str] = mapped_column(
        String(50),
        default="agent",
    )

    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        server_default=true(),
        nullable=False,
    )

    assigned_investigations: Mapped[list["Investigation"]] = relationship(
        back_populates="assigned_agent", foreign_keys="Investigation.assigned_agent_id"
    )
    assignments_as_agent: Mapped[list["InvestigationAssignment"]] = relationship(
        foreign_keys="InvestigationAssignment.agent_id", back_populates="agent"
    )
    assignments_created: Mapped[list["InvestigationAssignment"]] = relationship(
        foreign_keys="InvestigationAssignment.assigned_by_id", back_populates="assigned_by"
    )
    reports_authored: Mapped[list["InvestigationReport"]] = relationship(back_populates="author")
    reviews_authored: Mapped[list["InvestigationReview"]] = relationship(back_populates="reviewer")
