from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.assignment import InvestigationAssignment
    from app.models.report import InvestigationReport
    from app.models.review import InvestigationReview
    from app.models.user import User


class Investigation(Base):
    __tablename__ = "investigations"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'assigned', 'in_progress', 'under_review', "
            "'returned_for_correction', 'completed')",
            name="ck_investigations_status",
        ),
        CheckConstraint("priority IN ('normal', 'high', 'urgent')", name="ck_investigations_priority"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    reference_number: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    subject_name: Mapped[str] = mapped_column(String(255))
    legacy_address: Mapped[str | None] = mapped_column(String(500), nullable=True)
    house_number: Mapped[str | None] = mapped_column(String(100), nullable=True)
    unit_floor_building_name: Mapped[str | None] = mapped_column(String(150), nullable=True)
    street: Mapped[str | None] = mapped_column(String(200), nullable=True)
    subdivision_village_purok: Mapped[str | None] = mapped_column(String(200), nullable=True)
    region_code: Mapped[str | None] = mapped_column(String(10), nullable=True, index=True)
    province_code: Mapped[str | None] = mapped_column(String(10), nullable=True, index=True)
    city_municipality_code: Mapped[str | None] = mapped_column(String(10), nullable=True, index=True)
    barangay_code: Mapped[str | None] = mapped_column(String(10), nullable=True, index=True)
    postal_code: Mapped[str | None] = mapped_column(String(10), nullable=True)
    status: Mapped[str] = mapped_column(String(50), default="pending")
    priority: Mapped[str] = mapped_column(String(50), default="normal")
    assigned_agent_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)

    assignments: Mapped[list["InvestigationAssignment"]] = relationship(
        back_populates="investigation"
    )
    reports: Mapped[list["InvestigationReport"]] = relationship(
        back_populates="investigation", order_by="InvestigationReport.version"
    )
    reviews: Mapped[list["InvestigationReview"]] = relationship(
        back_populates="investigation"
    )
    assigned_agent: Mapped["User | None"] = relationship(
        foreign_keys=[assigned_agent_id], back_populates="assigned_investigations"
    )

    @property
    def address_display(self) -> str:
        from app.services.locations import address_display

        return address_display(self)

    @property
    def assigned_agent_name(self) -> str | None:
        return self.assigned_agent.name if self.assigned_agent else None
