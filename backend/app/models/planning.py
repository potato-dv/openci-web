from datetime import date, datetime

from sqlalchemy import Boolean, CheckConstraint, Date, DateTime, Float, ForeignKey, Index, Integer, JSON, String, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class PlanningRun(Base):
    __tablename__ = "planning_runs"
    __table_args__ = (
        CheckConstraint(
            "status IN ('queued', 'running', 'ready', 'failed', 'stale', 'applied')",
            name="ck_planning_runs_status",
        ),
        Index("ix_planning_runs_scope", "work_date", "region_code", "status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    requested_by_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), index=True)
    auto_publish: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=text("false"))
    auto_replan_requested: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=text("false"))
    auto_assignment_id: Mapped[int | None] = mapped_column(ForeignKey("investigation_assignments.id", ondelete="SET NULL"), nullable=True, index=True)
    auto_assignment_ids: Mapped[list[int]] = mapped_column(JSON, nullable=False, default=list, server_default=text("'[]'"))
    work_date: Mapped[date] = mapped_column(Date, nullable=False)
    region_code: Mapped[str] = mapped_column(String(10), nullable=False, index=True)
    investigation_ids: Mapped[list[int]] = mapped_column(JSON, nullable=False)
    agent_ids: Mapped[list[int]] = mapped_column(JSON, nullable=False)
    locked_assignments: Mapped[list[dict]] = mapped_column(JSON, nullable=False, default=list)
    movable_investigation_ids: Mapped[list[int]] = mapped_column(JSON, nullable=False, default=list, server_default=text("'[]'"))
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="queued", server_default=text("'queued'"), index=True)
    input_digest: Mapped[str | None] = mapped_column(String(64), nullable=True)
    result_digest: Mapped[str | None] = mapped_column(String(80), nullable=True)
    osrm_dataset: Mapped[str | None] = mapped_column(String(100), nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    warnings: Mapped[list[dict]] = mapped_column(JSON, nullable=False, default=list, server_default=text("'[]'"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("CURRENT_TIMESTAMP"))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    applied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AgentShift(Base):
    __tablename__ = "agent_shifts"
    __table_args__ = (
        UniqueConstraint("agent_id", "work_date", name="uq_agent_shifts_agent_date"),
        CheckConstraint("shift_ends_at > shift_starts_at", name="ck_agent_shifts_time_order"),
        CheckConstraint("max_visits > 0", name="ck_agent_shifts_max_visits_positive"),
        CheckConstraint("max_open_cases > 0", name="ck_agent_shifts_max_open_cases_positive"),
        CheckConstraint("source IN ('manual', 'recurring')", name="ck_agent_shifts_source"),
        CheckConstraint(
            "(break_starts_at IS NULL AND break_ends_at IS NULL) OR "
            "(break_starts_at IS NOT NULL AND break_ends_at IS NOT NULL "
            "AND break_ends_at > break_starts_at "
            "AND break_starts_at >= shift_starts_at AND break_ends_at <= shift_ends_at)",
            name="ck_agent_shifts_break_interval",
        ),
        CheckConstraint(
            "(last_completed_latitude IS NULL AND last_completed_longitude IS NULL) OR "
            "(last_completed_latitude BETWEEN -90 AND 90 AND last_completed_longitude BETWEEN -180 AND 180)",
            name="ck_agent_shifts_last_stop_coordinates",
        ),
        CheckConstraint(
            "(start_latitude IS NULL AND start_longitude IS NULL) OR "
            "(start_latitude BETWEEN -90 AND 90 AND start_longitude BETWEEN -180 AND 180)",
            name="ck_agent_shifts_start_coordinates",
        ),
        CheckConstraint(
            "(end_latitude IS NULL AND end_longitude IS NULL) OR "
            "(end_latitude IS NOT NULL AND end_longitude IS NOT NULL "
            "AND end_latitude BETWEEN -90 AND 90 AND end_longitude BETWEEN -180 AND 180)",
            name="ck_agent_shifts_end_coordinates",
        ),
        Index("ix_agent_shifts_date_region_available", "work_date", "region_code", "is_available"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    agent_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    work_date: Mapped[date] = mapped_column(Date, nullable=False)
    region_code: Mapped[str] = mapped_column(String(10), nullable=False)
    source: Mapped[str] = mapped_column(String(20), nullable=False, default="manual", server_default=text("'manual'"))
    schedule_version_id: Mapped[int | None] = mapped_column(ForeignKey("agent_weekly_schedules.id", ondelete="SET NULL"), nullable=True)
    is_available: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default=text("true"))
    shift_starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    shift_ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    break_starts_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    break_ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    start_latitude: Mapped[float] = mapped_column(Float, nullable=False)
    start_longitude: Mapped[float] = mapped_column(Float, nullable=False)
    end_latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    end_longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    start_location_label: Mapped[str | None] = mapped_column(String(500), nullable=True)
    start_location_source: Mapped[str | None] = mapped_column(String(20), nullable=True)
    start_location_provider_ref: Mapped[str | None] = mapped_column(String(100), nullable=True)
    end_location_label: Mapped[str | None] = mapped_column(String(500), nullable=True)
    end_location_source: Mapped[str | None] = mapped_column(String(20), nullable=True)
    end_location_provider_ref: Mapped[str | None] = mapped_column(String(100), nullable=True)
    last_completed_investigation_id: Mapped[int | None] = mapped_column(ForeignKey("investigations.id", ondelete="SET NULL"), nullable=True)
    last_completed_report_id: Mapped[int | None] = mapped_column(ForeignKey("investigation_reports.id", ondelete="SET NULL"), nullable=True)
    last_completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_completed_latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    last_completed_longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    last_attempted_investigation_id: Mapped[int | None] = mapped_column(ForeignKey("investigations.id", ondelete="SET NULL"), nullable=True)
    last_attempted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_attempted_latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    last_attempted_longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    max_visits: Mapped[int] = mapped_column(Integer, nullable=False)
    max_open_cases: Mapped[int] = mapped_column(Integer, nullable=False)
    current_planning_run_id: Mapped[int | None] = mapped_column(ForeignKey("planning_runs.id", ondelete="SET NULL"), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("CURRENT_TIMESTAMP"), onupdate=text("CURRENT_TIMESTAMP"))


class PlanningItem(Base):
    __tablename__ = "planning_items"
    __table_args__ = (
        UniqueConstraint("planning_run_id", "investigation_id", name="uq_planning_items_run_investigation"),
        CheckConstraint("outcome IN ('assigned', 'unassigned')", name="ck_planning_items_outcome"),
        Index("ix_planning_items_route", "planning_run_id", "agent_id", "sequence"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    planning_run_id: Mapped[int] = mapped_column(ForeignKey("planning_runs.id", ondelete="CASCADE"), nullable=False)
    investigation_id: Mapped[int] = mapped_column(ForeignKey("investigations.id", ondelete="CASCADE"), nullable=False)
    agent_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    outcome: Mapped[str] = mapped_column(String(20), nullable=False)
    reason: Mapped[str | None] = mapped_column(String(100), nullable=True)
    sequence: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # OSRM estimate assuming departure as soon as the route allows; retained for API compatibility.
    estimated_arrival_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # VROOM job-step arrival. Null for historical plans whose raw VROOM arrival was not saved.
    planned_arrival_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    travel_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    travel_metres: Mapped[int | None] = mapped_column(Integer, nullable=True)
    estimated_service_start_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # New plans store VROOM job-step waiting_time here; historical values are not VROOM waits.
    waiting_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    prior_assignment_id: Mapped[int | None] = mapped_column(ForeignKey("investigation_assignments.id", ondelete="SET NULL"), nullable=True)
    applied_assignment_id: Mapped[int | None] = mapped_column(ForeignKey("investigation_assignments.id", ondelete="SET NULL"), nullable=True)



class PlanningRoute(Base):
    __tablename__ = "planning_routes"
    __table_args__ = (
        UniqueConstraint("planning_run_id", "agent_id", name="uq_planning_routes_run_agent"),
        CheckConstraint("geometry_status IN ('ready', 'failed')", name="ck_planning_routes_geometry_status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    planning_run_id: Mapped[int] = mapped_column(ForeignKey("planning_runs.id", ondelete="CASCADE"), index=True)
    agent_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    geometry_status: Mapped[str] = mapped_column(String(20), nullable=False)
    geometry_error_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    geometry: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    geometry_digest: Mapped[str | None] = mapped_column(String(64), nullable=True)
    total_distance_metres: Mapped[int | None] = mapped_column(Integer, nullable=True)
    total_travel_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    total_service_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    total_waiting_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    total_break_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # VROOM start-step arrival plus waiting_time; null for historical plans.
    planned_departure_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    start: Mapped[dict] = mapped_column(JSON, nullable=False)
    end: Mapped[dict | None] = mapped_column(JSON, nullable=True)
