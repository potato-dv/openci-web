from datetime import date, datetime

from sqlalchemy import Boolean, CheckConstraint, Date, DateTime, Float, ForeignKey, Index, Integer, JSON, String, Time, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class AgentWorkProfile(Base):
    __tablename__ = "agent_work_profiles"
    __table_args__ = (
        UniqueConstraint("agent_id", name="uq_agent_work_profiles_agent"),
        CheckConstraint(
            "(depot_latitude IS NULL AND depot_longitude IS NULL) OR "
            "(depot_latitude BETWEEN -90 AND 90 AND depot_longitude BETWEEN -180 AND 180)",
            name="ck_agent_work_profiles_depot_coordinates",
        ),
        CheckConstraint(
            "(end_latitude IS NULL AND end_longitude IS NULL) OR "
            "(end_latitude IS NOT NULL AND end_longitude IS NOT NULL "
            "AND end_latitude BETWEEN -90 AND 90 AND end_longitude BETWEEN -180 AND 180)",
            name="ck_agent_work_profiles_end_coordinates",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    agent_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    depot_latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    depot_longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    depot_label: Mapped[str | None] = mapped_column(String(500), nullable=True)
    depot_source: Mapped[str | None] = mapped_column(String(20), nullable=True)
    depot_provider_ref: Mapped[str | None] = mapped_column(String(100), nullable=True)
    end_latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    end_longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    end_label: Mapped[str | None] = mapped_column(String(500), nullable=True)
    end_source: Mapped[str | None] = mapped_column(String(20), nullable=True)
    end_provider_ref: Mapped[str | None] = mapped_column(String(100), nullable=True)
    updated_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("CURRENT_TIMESTAMP"), onupdate=text("CURRENT_TIMESTAMP"))

class AgentWeeklySchedule(Base):
    __tablename__ = "agent_weekly_schedules"
    __table_args__ = (
        UniqueConstraint("agent_id", "effective_from", name="uq_agent_weekly_schedules_agent_start"),
        CheckConstraint("effective_until IS NULL OR effective_until >= effective_from", name="ck_agent_weekly_schedules_effective_range"),
        CheckConstraint("max_visits > 0", name="ck_agent_weekly_schedules_max_visits_positive"),
        CheckConstraint("max_open_cases > 0", name="ck_agent_weekly_schedules_max_open_cases_positive"),
        Index("ix_agent_weekly_schedules_agent_effective", "agent_id", "effective_from", "effective_until"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    agent_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    effective_from: Mapped[date] = mapped_column(Date, nullable=False)
    effective_until: Mapped[date | None] = mapped_column(Date, nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default=text("true"))
    region_code: Mapped[str] = mapped_column(String(10), nullable=False)
    max_visits: Mapped[int] = mapped_column(Integer, nullable=False, default=8, server_default=text("8"))
    max_open_cases: Mapped[int] = mapped_column(Integer, nullable=False, default=20, server_default=text("20"))
    days: Mapped[list[dict]] = mapped_column(JSON, nullable=False, default=list)
    updated_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("CURRENT_TIMESTAMP"))


class PlanningTrigger(Base):
    __tablename__ = "planning_triggers"
    __table_args__ = (
        UniqueConstraint("work_date", "region_code", name="uq_planning_triggers_scope"),
        CheckConstraint("status IN ('pending', 'processing', 'retry', 'complete', 'failed')", name="ck_planning_triggers_status"),
        Index("ix_planning_triggers_dispatch", "status", "next_attempt_at", "work_date"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    work_date: Mapped[date] = mapped_column(Date, nullable=False)
    region_code: Mapped[str] = mapped_column(String(10), nullable=False)
    reasons: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    generation: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default=text("1"))
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default=text("0"))
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending", server_default=text("'pending'"))
    last_error: Mapped[str | None] = mapped_column(String(120), nullable=True)
    input_fingerprint: Mapped[str | None] = mapped_column(String(64), nullable=True)
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("CURRENT_TIMESTAMP"), onupdate=text("CURRENT_TIMESTAMP"))
