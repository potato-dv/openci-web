from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, ForeignKeyConstraint, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.investigation import Investigation
    from app.models.report import InvestigationReport
    from app.models.user import User


class InvestigationReview(Base):
    __tablename__ = "investigation_reviews"
    __table_args__ = (
        CheckConstraint("decision IN ('approved', 'returned_for_correction')", name="ck_investigation_reviews_decision"),
        ForeignKeyConstraint(
            ["report_id", "investigation_id"],
            ["investigation_reports.id", "investigation_reports.investigation_id"],
            ondelete="CASCADE",
            name="fk_reviews_report_investigation",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    investigation_id: Mapped[int] = mapped_column(
        ForeignKey("investigations.id", ondelete="CASCADE"),
        index=True,
    )
    report_id: Mapped[int] = mapped_column(Integer, index=True)
    reviewer_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), index=True)
    decision: Mapped[str] = mapped_column(String(32))
    comments: Mapped[str | None] = mapped_column(Text, nullable=True)
    reviewed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )
    investigation: Mapped["Investigation"] = relationship(back_populates="reviews", overlaps="reviews")
    report: Mapped["InvestigationReport"] = relationship(
        back_populates="reviews", foreign_keys="[InvestigationReview.report_id, InvestigationReview.investigation_id]",
        overlaps="investigation,reviews",
    )
    reviewer: Mapped["User"] = relationship(back_populates="reviews_authored")

    @property
    def reviewer_name(self) -> str:
        return self.reviewer.name
