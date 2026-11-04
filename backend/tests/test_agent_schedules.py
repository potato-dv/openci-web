import unittest
from datetime import date, datetime, time, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.database import Base
import app.models  # Register every mapped table before create_all.
from app.models import AgentShift, AgentWeeklySchedule, PlanningTrigger, User
from app.schemas.planning import AgentWorkProfileInput, WeeklyScheduleDayInput, WeeklyScheduleInput
from app.routes.planning import delete_agent_shift_override
from app.services.agent_schedules import (
    MANILA,
    availability_preview,
    dispatch_planning_triggers,
    enqueue_planning_trigger,
    materialize_work_date,
    resolve_availability_day,
    save_weekly_schedule,
    save_work_profile,
)


class AgentScheduleTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)

    def tearDown(self):
        self.engine.dispose()

    def test_materialization_is_idempotent_and_keeps_the_daily_snapshot(self):
        work_date = datetime.now(MANILA).date() + timedelta(days=1)
        with Session(self.engine) as db:
            supervisor = User(name="Supervisor", email="schedule-supervisor@example.test", password="hash", role="supervisor")
            agent = User(name="Agent", email="schedule-agent@example.test", password="hash", role="agent", is_active=True)
            db.add_all([supervisor, agent])
            db.flush()
            profile = AgentWorkProfileInput(
                depot_latitude=14.6,
                depot_longitude=121.1,
                depot_label="Main depot",
                depot_source="manual",
            )
            save_work_profile(db, agent.id, supervisor, profile)
            schedule_input = WeeklyScheduleInput(
                effective_from=work_date,
                enabled=True,
                region_code="ALL",
                max_visits=8,
                max_open_cases=20,
                days=[
                    WeeklyScheduleDayInput(
                        weekday=weekday,
                        is_working=True,
                        shift_start=time(8),
                        shift_end=time(17),
                        break_start=time(12),
                        break_end=time(13),
                    )
                    for weekday in range(7)
                ],
            )
            schedule = save_weekly_schedule(db, agent.id, supervisor, schedule_input)
            db.commit()

            self.assertEqual(materialize_work_date(db, work_date), 1)
            self.assertEqual(materialize_work_date(db, work_date), 0)
            shift = db.query(AgentShift).filter_by(agent_id=agent.id, work_date=work_date).one()
            self.assertEqual(shift.source, "recurring")
            self.assertEqual(shift.schedule_version_id, schedule.id)
            self.assertEqual(shift.region_code, "ALL")
            self.assertEqual(shift.start_location_label, "Main depot")
            self.assertEqual(shift.shift_starts_at.replace(tzinfo=timezone.utc).hour, 0)
            self.assertEqual(shift.break_starts_at.replace(tzinfo=timezone.utc).hour, 4)

            shift.last_completed_at = datetime.combine(work_date, time(10), tzinfo=MANILA).astimezone(timezone.utc)
            shift.last_completed_latitude = 14.7
            shift.last_completed_longitude = 121.2
            db.commit()
            next_work_date = work_date + timedelta(days=1)
            self.assertEqual(materialize_work_date(db, next_work_date), 1)
            next_shift = db.query(AgentShift).filter_by(agent_id=agent.id, work_date=next_work_date).one()
            self.assertEqual((next_shift.start_latitude, next_shift.start_longitude), (14.6, 121.1))
            self.assertEqual(next_shift.start_location_label, "Main depot")
            self.assertIsNone(next_shift.last_completed_at)
            self.assertIsNone(next_shift.last_completed_latitude)
            self.assertIsNone(next_shift.last_completed_longitude)

            changed_days = [day.model_copy(update={"shift_start": time(9)} if day.weekday == 0 else {}) for day in schedule_input.days]
            save_weekly_schedule(
                db,
                agent.id,
                supervisor,
                schedule_input.model_copy(update={"days": changed_days}),
            )
            db.commit()

            preview = availability_preview(db, agent.id, work_date, work_date + timedelta(days=30))
            self.assertEqual(preview["days"][0]["status"], "scheduled")
            self.assertEqual(preview["days"][0]["shift_starts_at"].replace(tzinfo=timezone.utc).hour, 0)

    def test_trigger_coalesces_reasons_and_all_region_schedule_promotes_scope(self):
        work_date = date(2026, 11, 2)
        with Session(self.engine) as db:
            supervisor = User(name="Supervisor", email="trigger-supervisor@example.test", password="hash", role="supervisor")
            agent = User(name="Agent", email="trigger-agent@example.test", password="hash", role="agent", is_active=True)
            db.add_all([supervisor, agent])
            db.flush()
            schedule = AgentWeeklySchedule(
                agent_id=agent.id,
                effective_from=work_date,
                enabled=True,
                region_code="ALL",
                max_visits=8,
                max_open_cases=20,
                days=[{"weekday": work_date.weekday(), "is_working": True}],
            )
            db.add(schedule)
            db.flush()

            trigger = enqueue_planning_trigger(db, work_date, "1300000000", "location_confirmed")
            enqueue_planning_trigger(db, work_date, "1300000000", "agent_activated")
            db.commit()

            saved = db.query(PlanningTrigger).one()
            self.assertEqual(trigger.region_code, "ALL")
            self.assertEqual(saved.generation, 2)
            self.assertEqual(saved.reasons, ["location_confirmed", "agent_activated"])
            self.assertEqual(saved.status, "pending")

    def test_trigger_retries_when_the_task_broker_is_unavailable(self):
        work_date = date(2026, 11, 2)
        with Session(self.engine) as db:
            supervisor = User(name="Supervisor", email="retry-supervisor@example.test", password="hash", role="supervisor", is_active=True)
            db.add(supervisor)
            db.flush()
            enqueue_planning_trigger(db, work_date, "1300000000", "location_confirmed")
            db.commit()

            failed_run = SimpleNamespace(status="failed", error_code="queue_unavailable", input_digest=None)
            with patch("app.services.planning.queue_automatic_planning", return_value=failed_run):
                summary = dispatch_planning_triggers(db)

            trigger = db.query(PlanningTrigger).one()
            self.assertEqual(summary["retried"], 1)
            self.assertEqual(trigger.status, "retry")
            self.assertEqual(trigger.attempts, 1)
            self.assertEqual(trigger.last_error, "queue_unavailable")
            self.assertIsNotNone(trigger.next_attempt_at)

    def test_removing_a_manual_override_restores_today_schedule_and_triggers_its_region(self):
        work_date = datetime.now(MANILA).date()
        with Session(self.engine) as db:
            supervisor = User(name="Supervisor", email="override-supervisor@example.test", password="hash", role="supervisor")
            agent = User(name="Agent", email="override-agent@example.test", password="hash", role="agent", is_active=True)
            db.add_all([supervisor, agent])
            db.flush()
            save_work_profile(db, agent.id, supervisor, AgentWorkProfileInput(
                depot_latitude=14.6,
                depot_longitude=121.1,
                depot_source="manual",
            ))
            days = [
                WeeklyScheduleDayInput(
                    weekday=weekday,
                    is_working=True,
                    shift_start=time(8),
                    shift_end=time(17),
                )
                for weekday in range(7)
            ]
            save_weekly_schedule(db, agent.id, supervisor, WeeklyScheduleInput(
                effective_from=work_date,
                enabled=True,
                region_code="1300000000",
                max_visits=8,
                max_open_cases=20,
                days=days,
            ))
            db.add(AgentShift(
                agent_id=agent.id,
                work_date=work_date,
                region_code="ALL",
                is_available=True,
                shift_starts_at=datetime.combine(work_date, time(8), tzinfo=MANILA).astimezone(timezone.utc),
                shift_ends_at=datetime.combine(work_date, time(17), tzinfo=MANILA).astimezone(timezone.utc),
                start_latitude=14.6,
                start_longitude=121.1,
                max_visits=8,
                max_open_cases=20,
            ))
            db.commit()

            delete_agent_shift_override(agent.id, work_date, db, supervisor)

            restored = db.query(AgentShift).filter_by(agent_id=agent.id, work_date=work_date).one()
            trigger = db.query(PlanningTrigger).one()
            self.assertEqual(restored.source, "recurring")
            self.assertEqual(restored.region_code, "1300000000")
            self.assertEqual(trigger.region_code, "1300000000")


if __name__ == "__main__":
    unittest.main()
