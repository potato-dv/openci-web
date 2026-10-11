from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class InvestigationReview(Base):
    __tablename__ = "investigation_reviews"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    investigation_id: Mapped[int] = mapped_column(
        ForeignKey("investigations.id"),
        index=True,
    )
    report_id: Mapped[int] = mapped_column(ForeignKey("investigation_reports.id"))
    reviewer_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    decision: Mapped[str] = mapped_column(String(20))
    comments: Mapped[str | None] = mapped_column(Text, nullable=True)
    reviewed_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
    )