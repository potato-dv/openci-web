from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class InvestigationReport(Base):
    __tablename__ = "investigation_reports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    investigation_id: Mapped[int] = mapped_column(
        ForeignKey("investigations.id"),
        unique=True,
        index=True,
    )
    author_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    content: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="draft")
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )
    submitted_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
    )