from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import or_, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.agent_schedule import AgentWeeklySchedule, AgentWorkProfile, PlanningTrigger
from app.models.planning import AgentShift
from app.models.user import User
from app.services.locations import catalog

MANILA = ZoneInfo("Asia/Manila")
ALL_REGIONS = "ALL"


def _valid_region(region_code: str) -> bool:
    return region_code == ALL_REGIONS or region_code in catalog()["region_codes"]


def get_work_profile(db: Session, agent_id: int) -> AgentWorkProfile | None:
    return db.query(AgentWorkProfile).filter(AgentWorkProfile.agent_id == agent_id).first()


def save_work_profile(db: Session, agent_id: int, actor: User, values) -> AgentWorkProfile:
    agent = db.query(User).filter(User.id == agent_id, User.role == "agent").with_for_update().first()
    if agent is None:
        raise ValueError("agent_not_found")
    has_enabled_schedule = db.query(AgentWeeklySchedule.id).filter(
        AgentWeeklySchedule.agent_id == agent_id,
        AgentWeeklySchedule.enabled.is_(True),
    ).first() is not None
    if has_enabled_schedule and values.depot_latitude is None:
        raise ValueError("depot_required_for_enabled_schedule")
    profile = get_work_profile(db, agent_id)
    if profile is None:
        profile = AgentWorkProfile(agent_id=agent_id)
        db.add(profile)
    for field, value in values.model_dump().items():
        setattr(profile, field, value)
    profile.updated_by_id = actor.id
    db.flush()
    return profile


def get_weekly_schedule(db: Session, agent_id: int, on_date: date | None = None) -> AgentWeeklySchedule | None:
    on_date = on_date or datetime.now(MANILA).date()
    return db.query(AgentWeeklySchedule).filter(
        AgentWeeklySchedule.agent_id == agent_id,
        AgentWeeklySchedule.effective_from <= on_date,
        (AgentWeeklySchedule.effective_until.is_(None) | (AgentWeeklySchedule.effective_until >= on_date)),
    ).order_by(AgentWeeklySchedule.effective_from.desc()).first()


def save_weekly_schedule(db: Session, agent_id: int, actor: User, values) -> AgentWeeklySchedule:
    agent = db.query(User).filter(User.id == agent_id, User.role == "agent").with_for_update().first()
    if agent is None:
        raise ValueError("agent_not_found")
    if not _valid_region(values.region_code):
        raise ValueError("invalid_region")
    profile = get_work_profile(db, agent_id)
    if values.enabled and (profile is None or profile.depot_latitude is None or profile.depot_longitude is None):
        raise ValueError("depot_required_for_enabled_schedule")

    rows = db.query(AgentWeeklySchedule).filter(
        AgentWeeklySchedule.agent_id == agent_id,
    ).order_by(AgentWeeklySchedule.effective_from).with_for_update().all()
    row = next((item for item in rows if item.effective_from == values.effective_from), None)
    if row is None:
        row = AgentWeeklySchedule(agent_id=agent_id, effective_from=values.effective_from)
        db.add(row)
        rows.append(row)
    rows.sort(key=lambda item: (item.effective_from, item.id or 0))
    index = rows.index(row)
    row.effective_until = rows[index + 1].effective_from - timedelta(days=1) if index + 1 < len(rows) else None
    if index:
        rows[index - 1].effective_until = values.effective_from - timedelta(days=1)
    for next_index in range(index + 1, len(rows)):
        previous = rows[next_index - 1]
        rows[next_index].effective_until = rows[next_index + 1].effective_from - timedelta(days=1) if next_index + 1 < len(rows) else None
        previous.effective_until = rows[next_index].effective_from - timedelta(days=1)

    row.enabled = values.enabled
    row.region_code = values.region_code
    row.max_visits = values.max_visits
    row.max_open_cases = values.max_open_cases
    row.days = [item.model_dump(mode="json") for item in sorted(values.days, key=lambda day: day.weekday)]
    row.updated_by_id = actor.id
    today = datetime.now(MANILA).date()
    if not values.enabled and values.effective_from <= today:
        generated_shift = db.query(AgentShift).filter(
            AgentShift.agent_id == agent_id,
            AgentShift.work_date == today,
            AgentShift.source == "recurring",
        ).with_for_update().first()
        if generated_shift is not None:
            generated_shift.is_available = False
            generated_shift.current_planning_run_id = None
    db.flush()
    return row


def _local_instant(day: date, clock: str | time | None) -> datetime | None:
    if clock is None:
        return None
    if isinstance(clock, str):
        clock = time.fromisoformat(clock)
    return datetime.combine(day, clock, tzinfo=MANILA).astimezone(ZoneInfo("UTC"))


def _scheduled_day(db: Session, agent_id: int, work_date: date) -> tuple[AgentWeeklySchedule | None, dict | None]:
    schedule = get_weekly_schedule(db, agent_id, work_date)
    if schedule is None or not schedule.enabled:
        return schedule, None
    day = next((item for item in schedule.days or [] if int(item.get("weekday", -1)) == work_date.weekday()), None)
    return schedule, day


def resolve_availability_day(db: Session, agent_id: int, work_date: date) -> dict:
    manual_or_materialized = db.query(AgentShift).filter(
        AgentShift.agent_id == agent_id,
        AgentShift.work_date == work_date,
    ).first()
    if manual_or_materialized is not None and manual_or_materialized.source == "manual":
        return {
            "work_date": work_date, "status": "manual_override", "source": "manual",
            "region_code": manual_or_materialized.region_code, "is_available": manual_or_materialized.is_available,
            "shift_starts_at": manual_or_materialized.shift_starts_at, "shift_ends_at": manual_or_materialized.shift_ends_at,
            "break_starts_at": manual_or_materialized.break_starts_at, "break_ends_at": manual_or_materialized.break_ends_at,
            "start_latitude": manual_or_materialized.start_latitude, "start_longitude": manual_or_materialized.start_longitude,
            "start_location_label": manual_or_materialized.start_location_label,
            "max_visits": manual_or_materialized.max_visits, "max_open_cases": manual_or_materialized.max_open_cases,
        }
    if manual_or_materialized is not None and manual_or_materialized.source == "recurring":
        if not manual_or_materialized.is_available:
            return {"work_date": work_date, "status": "not_configured", "source": "recurring", "region_code": manual_or_materialized.region_code, "is_available": False}
        return {
            "work_date": work_date, "status": "scheduled", "source": "recurring",
            "region_code": manual_or_materialized.region_code, "is_available": True,
            "shift_starts_at": manual_or_materialized.shift_starts_at, "shift_ends_at": manual_or_materialized.shift_ends_at,
            "break_starts_at": manual_or_materialized.break_starts_at, "break_ends_at": manual_or_materialized.break_ends_at,
            "start_latitude": manual_or_materialized.start_latitude, "start_longitude": manual_or_materialized.start_longitude,
            "start_location_label": manual_or_materialized.start_location_label,
            "max_visits": manual_or_materialized.max_visits, "max_open_cases": manual_or_materialized.max_open_cases,
        }
    schedule, day = _scheduled_day(db, agent_id, work_date)
    if schedule is None or not schedule.enabled:
        return {"work_date": work_date, "status": "not_configured", "source": None, "is_available": False}
    if not day or not day.get("is_working"):
        return {"work_date": work_date, "status": "day_off", "source": "recurring", "region_code": schedule.region_code, "is_available": False}
    profile = get_work_profile(db, agent_id)
    return {
        "work_date": work_date, "status": "scheduled", "source": "recurring", "region_code": schedule.region_code,
        "is_available": bool(profile and profile.depot_latitude is not None and profile.depot_longitude is not None),
        "shift_starts_at": _local_instant(work_date, day.get("shift_start")),
        "shift_ends_at": _local_instant(work_date, day.get("shift_end")),
        "break_starts_at": _local_instant(work_date, day.get("break_start")),
        "break_ends_at": _local_instant(work_date, day.get("break_end")),
        "start_latitude": profile.depot_latitude if profile else None,
        "start_longitude": profile.depot_longitude if profile else None,
        "start_location_label": profile.depot_label if profile else None,
        "max_visits": schedule.max_visits, "max_open_cases": schedule.max_open_cases,
    }


def availability_preview(db: Session, agent_id: int, from_date: date, to_date: date) -> dict:
    if to_date < from_date:
        raise ValueError("invalid_date_range")
    if (to_date - from_date).days >= 31:
        raise ValueError("availability_range_exceeds_31_days")
    return {
        "agent_id": agent_id,
        "from_date": from_date,
        "to_date": to_date,
        "days": [resolve_availability_day(db, agent_id, from_date + timedelta(days=offset)) for offset in range((to_date - from_date).days + 1)],
    }


def materialize_work_date(db: Session, work_date: date) -> int:
    agents = db.query(User).filter(User.role == "agent", User.is_active.is_(True)).order_by(User.id).all()
    created = 0
    for agent in agents:
        if db.get_bind().dialect.name == "postgresql":
            db.execute(text("SELECT pg_advisory_xact_lock(hashtext(:scope_key), 19472)"), {
                "scope_key": f"recurring-agent-shift:{work_date.isoformat()}:{agent.id}",
            })
        existing = db.query(AgentShift).filter(AgentShift.agent_id == agent.id, AgentShift.work_date == work_date).with_for_update().first()
        if existing is not None:
            continue
        schedule, day = _scheduled_day(db, agent.id, work_date)
        profile = get_work_profile(db, agent.id)
        if not schedule or not schedule.enabled or not day or not day.get("is_working") or not profile or profile.depot_latitude is None or profile.depot_longitude is None:
            continue
        shift = AgentShift(
            agent_id=agent.id,
            work_date=work_date,
            region_code=schedule.region_code,
            source="recurring",
            schedule_version_id=schedule.id,
            is_available=True,
            shift_starts_at=_local_instant(work_date, day.get("shift_start")),
            shift_ends_at=_local_instant(work_date, day.get("shift_end")),
            break_starts_at=_local_instant(work_date, day.get("break_start")),
            break_ends_at=_local_instant(work_date, day.get("break_end")),
            start_latitude=profile.depot_latitude,
            start_longitude=profile.depot_longitude,
            end_latitude=profile.end_latitude,
            end_longitude=profile.end_longitude,
            start_location_label=profile.depot_label,
            start_location_source=profile.depot_source,
            start_location_provider_ref=profile.depot_provider_ref,
            end_location_label=profile.end_label,
            end_location_source=profile.end_source,
            end_location_provider_ref=profile.end_provider_ref,
            max_visits=schedule.max_visits,
            max_open_cases=schedule.max_open_cases,
        )
        try:
            with db.begin_nested():
                db.add(shift)
                db.flush()
            created += 1
        except IntegrityError:
            # Another scheduler/event request materialized this unique day row.
            continue
    db.flush()
    return created


def enqueue_planning_trigger(db: Session, work_date: date, region_code: str | None, reason: str) -> PlanningTrigger:
    scope = region_code or ALL_REGIONS
    if db.get_bind().dialect.name == "postgresql":
        # Serialize scope promotion and the unique-row upsert for this date.
        # Schedule/shift changes may turn a regional trigger into a global one.
        db.execute(text("SELECT pg_advisory_xact_lock(hashtext(:scope_key), 19473)"), {
            "scope_key": f"planning-trigger:{work_date.isoformat()}",
        })
    all_region_shift = db.query(AgentShift.id).join(
        User, User.id == AgentShift.agent_id,
    ).filter(
        AgentShift.work_date == work_date,
        AgentShift.region_code == ALL_REGIONS,
        AgentShift.is_available.is_(True),
        User.role == "agent",
        User.is_active.is_(True),
    ).first() is not None
    all_region_schedules = db.query(AgentWeeklySchedule).join(
        User, User.id == AgentWeeklySchedule.agent_id,
    ).filter(
        AgentWeeklySchedule.region_code == ALL_REGIONS,
        AgentWeeklySchedule.enabled.is_(True),
        AgentWeeklySchedule.effective_from <= work_date,
        (AgentWeeklySchedule.effective_until.is_(None) | (AgentWeeklySchedule.effective_until >= work_date)),
        User.role == "agent",
        User.is_active.is_(True),
    ).all()
    all_region_schedule = any(
        any(
            int(day.get("weekday", -1)) == work_date.weekday()
            and bool(day.get("is_working"))
            for day in schedule.days or []
        )
        for schedule in all_region_schedules
    )
    if all_region_shift or all_region_schedule:
        scope = ALL_REGIONS
    trigger = db.query(PlanningTrigger).filter(
        PlanningTrigger.work_date == work_date,
        PlanningTrigger.region_code == scope,
    ).with_for_update().first()
    if trigger is None:
        trigger = PlanningTrigger(work_date=work_date, region_code=scope, reasons=[reason], status="pending")
        db.add(trigger)
    else:
        trigger.generation += 1
        trigger.reasons = list(dict.fromkeys([*(trigger.reasons or []), reason]))[-20:]
        trigger.status = "pending"
        trigger.attempts = 0
        trigger.last_error = None
        trigger.next_attempt_at = None
        trigger.input_fingerprint = None
    db.flush()
    return trigger


def dispatch_planning_triggers(db: Session, limit: int = 25) -> dict[str, int]:
    """Dispatch durable planning scopes; a committed trigger survives broker loss."""
    from app.models.planning import PlanningRun
    from app.services.planning import queue_automatic_planning

    now = datetime.now(timezone.utc)
    processing_lease_cutoff = now - timedelta(minutes=5)
    triggers = db.query(PlanningTrigger).filter(
        or_(
            PlanningTrigger.status.in_(("pending", "retry")),
            (PlanningTrigger.status == "processing") & (PlanningTrigger.updated_at <= processing_lease_cutoff),
        ),
        or_(PlanningTrigger.next_attempt_at.is_(None), PlanningTrigger.next_attempt_at <= now),
    ).order_by(PlanningTrigger.work_date, PlanningTrigger.id).with_for_update(skip_locked=True).limit(limit).all()
    summary = {"claimed": len(triggers), "completed": 0, "retried": 0, "failed": 0}
    for trigger in triggers:
        generation = trigger.generation
        trigger.status = "processing"
        trigger.attempts += 1
        trigger.next_attempt_at = None
        db.commit()
        try:
            requester = db.query(User).filter(
                User.is_active.is_(True),
                User.role.in_(("admin", "supervisor")),
            ).order_by(User.id).first()
            if requester is None:
                raise RuntimeError("planning_requester_unavailable")
            run = queue_automatic_planning(db, trigger.region_code, requester, trigger.work_date)
            db.refresh(trigger)
            if trigger.generation != generation:
                trigger.status = "pending"
            elif run and run.status == "failed" and run.error_code == "queue_unavailable":
                trigger.last_error = run.error_code
                if trigger.attempts >= 5:
                    trigger.status = "failed"
                    trigger.next_attempt_at = None
                    summary["failed"] += 1
                else:
                    delay = min(300 * (2 ** (trigger.attempts - 1)), 1800)
                    trigger.status = "retry"
                    trigger.next_attempt_at = now + timedelta(seconds=delay)
                    summary["retried"] += 1
            else:
                trigger.status = "complete"
                trigger.input_fingerprint = run.input_digest if run else None
                trigger.last_error = run.error_code if run and run.status == "failed" else None
                trigger.next_attempt_at = None
                summary["completed"] += 1
            db.commit()
        except Exception as error:
            db.rollback()
            trigger = db.query(PlanningTrigger).filter(PlanningTrigger.id == trigger.id).with_for_update().first()
            if trigger is None:
                continue
            if trigger.generation != generation:
                trigger.status = "pending"
            elif trigger.attempts >= 5:
                trigger.status = "failed"
                trigger.last_error = str(error)[:120] or "planning_dispatch_failed"
                trigger.next_attempt_at = None
                summary["failed"] += 1
            else:
                delay = min(300 * (2 ** (trigger.attempts - 1)), 1800)
                trigger.status = "retry"
                trigger.last_error = str(error)[:120] or "planning_dispatch_failed"
                trigger.next_attempt_at = now + timedelta(seconds=delay)
                summary["retried"] += 1
            db.commit()
    return summary
