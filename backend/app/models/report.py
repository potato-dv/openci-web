from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.investigation import Investigation
    from app.models.review import InvestigationReview
    from app.models.user import User


class InvestigationReport(Base):
    __tablename__ = "investigation_reports"
    __table_args__ = (
        CheckConstraint(
            "status IN ('draft', 'submitted', 'approved', 'returned_for_correction')",
            name="ck_investigation_reports_status",
        ),
        CheckConstraint("version > 0", name="ck_investigation_reports_version_positive"),
        CheckConstraint(
            "visit_outcome IS NULL OR visit_outcome IN ('visited', 'no_access', 'unable_to_locate')",
            name="ck_investigation_reports_visit_outcome",
        ),
        CheckConstraint(
            "outcome IS NULL OR outcome IN ('verified', 'not_verified', 'unable_to_verify', 'inconclusive')",
            name="ck_investigation_reports_outcome",
        ),
        CheckConstraint(
            "occupancy_status IS NULL OR occupancy_status IN ('occupied', 'vacant', 'unknown', 'not_applicable')",
            name="ck_investigation_reports_occupancy_status",
        ),
        UniqueConstraint("investigation_id", "version", name="uq_investigation_reports_investigation_version"),
        UniqueConstraint("id", "investigation_id", name="uq_report_id_investigation"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    investigation_id: Mapped[int] = mapped_column(
        ForeignKey("investigations.id", ondelete="CASCADE"),
        index=True,
    )
    author_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), index=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    content: Mapped[str] = mapped_column(Text)
    visit_outcome: Mapped[str | None] = mapped_column(String(30), nullable=True)
    outcome: Mapped[str | None] = mapped_column(String(30), nullable=True)
    verified_address: Mapped[str | None] = mapped_column(String(500), nullable=True)
    occupancy_status: Mapped[str | None] = mapped_column(String(30), nullable=True)
    property_condition: Mapped[str | None] = mapped_column(Text, nullable=True)
    interaction_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    visited_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(30), default="draft")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
    submitted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    investigation: Mapped["Investigation"] = relationship(back_populates="reports")
    reviews: Mapped[list["InvestigationReview"]] = relationship(back_populates="report", overlaps="investigation,reviews")
    author: Mapped["User"] = relationship(back_populates="reports_authored")

    @property
    def author_name(self) -> str:
        return self.author.name
