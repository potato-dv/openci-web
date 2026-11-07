from datetime import date, datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, CheckConstraint, Date, DateTime, Float, ForeignKey, Index, Integer, String, text
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
            "'returned_for_correction', 'completed', 'cancelled')",
            name="ck_investigations_status",
        ),
        CheckConstraint(
            "(status = 'cancelled' AND reopen_on IS NOT NULL) OR "
            "(status <> 'cancelled' AND reopen_on IS NULL)",
            name="ck_investigations_reopen_on_status",
        ),
        CheckConstraint("priority IN ('normal', 'high', 'urgent')", name="ck_investigations_priority"),
        CheckConstraint(
            "(latitude IS NULL AND longitude IS NULL) OR "
            "(latitude IS NOT NULL AND longitude IS NOT NULL "
            "AND latitude BETWEEN -90 AND 90 AND longitude BETWEEN -180 AND 180)",
            name="ck_investigations_coordinate_pair",
        ),
        CheckConstraint(
            "(latitude IS NULL AND longitude IS NULL AND location_source IS NULL AND location_confirmed_at IS NULL) OR "
            "(latitude IS NOT NULL AND longitude IS NOT NULL AND location_source IS NOT NULL "
            "AND location_source IN ('nominatim', 'manual') "
            "AND location_confirmed_at IS NOT NULL)",
            name="ck_investigations_location_confirmation",
        ),
        CheckConstraint(
            "(latitude IS NULL AND h3_r7 IS NULL AND h3_r8 IS NULL AND h3_r9 IS NULL) OR "
            "(latitude IS NOT NULL AND h3_r7 IS NOT NULL AND h3_r8 IS NOT NULL AND h3_r9 IS NOT NULL)",
            name="ck_investigations_h3_matches_location",
        ),
        CheckConstraint("service_duration_seconds > 0", name="ck_investigations_service_duration_positive"),
        CheckConstraint(
            "visit_not_before_at IS NULL OR visit_due_at IS NULL OR visit_due_at > visit_not_before_at",
            name="ck_investigations_visit_window_order",
        ),
        Index("ix_investigations_h3_r7", "h3_r7"),
        Index("ix_investigations_h3_r8", "h3_r8"),
        Index("ix_investigations_h3_r9", "h3_r9"),
        CheckConstraint(
            "(legacy_subject_name IS NOT NULL AND first_name IS NULL AND middle_name IS NULL AND last_name IS NULL) "
            "OR (legacy_subject_name IS NULL "
            "AND first_name IS NOT NULL AND length(trim(first_name)) > 0 "
            "AND last_name IS NOT NULL AND length(trim(last_name)) > 0 "
            "AND (middle_name IS NULL OR length(trim(middle_name)) > 0) "
            "AND length(trim(first_name)) + length(trim(last_name)) "
            "+ coalesce(length(trim(middle_name)), 0) "
            "+ CASE WHEN middle_name IS NULL THEN 1 ELSE 2 END <= 255)",
            name="ck_investigations_structured_subject_name",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    reference_number: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    first_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    middle_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    last_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    legacy_subject_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
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
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    location_source: Mapped[str | None] = mapped_column(String(20), nullable=True)
    location_provider_ref: Mapped[str | None] = mapped_column(String(100), nullable=True)
    location_confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    location_confirmed_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    h3_r7: Mapped[str | None] = mapped_column(String(15), nullable=True)
    h3_r8: Mapped[str | None] = mapped_column(String(15), nullable=True)
    h3_r9: Mapped[str | None] = mapped_column(String(15), nullable=True)
    service_duration_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=2700, server_default=text("2700"))
    visit_not_before_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    visit_due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(50), default="pending")
    reopen_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    priority: Mapped[str] = mapped_column(String(50), default="normal")
    assigned_agent_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    manual_assignment_required: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default=text("false"),
    )
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
    def location_confirmed(self) -> bool:
        return (
            self.latitude is not None
            and self.longitude is not None
            and self.location_source in {"nominatim", "manual"}
            and self.location_confirmed_at is not None
        )

    @property
    def assigned_agent_name(self) -> str | None:
        return self.assigned_agent.name if self.assigned_agent else None

    @property
    def subject_name(self) -> str:
        if self.legacy_subject_name is not None:
            return self.legacy_subject_name

        return " ".join(
            part.strip()
            for part in (self.first_name, self.middle_name, self.last_name)
            if part and part.strip()
        )
