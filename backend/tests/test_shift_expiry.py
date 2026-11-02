import unittest
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.database import Base
import app.models  # Register every table before create_all.
from app.models import (
    ActivityLog,
    AgentShift,
    Investigation,
    InvestigationAssignment,
    InvestigationReport,
    PlanningRun,
    PlanningTrigger,
    User,
)
from app.schemas.planning import AgentRouteResponse, PlanningMapDataResponse
from app.services.investigation import submit_report
from app.services.planning import planning_map_data
from app.services.shift_expiry import process_shift_end_investigations
from app.routes.investigation import get_investigations
from app.routes.planning import published_agent_route


MANILA = ZoneInfo("Asia/Manila")
REGION = "1300000000"


def local_instant(work_date: date, hour: int, minute: int = 0) -> datetime:
    return datetime.combine(work_date, time(hour, minute), tzinfo=MANILA)


class ShiftEndInvestigationTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)

    def tearDown(self):
        self.engine.dispose()

    def create_people(self, db: Session):
        supervisor = User(name="Supervisor", email="shift-supervisor@example.test", password="hash", role="supervisor")
        agent = User(name="Agent", email="shift-agent@example.test", password="hash", role="agent")
        other_agent = User(name="Other Agent", email="shift-other-agent@example.test", password="hash", role="agent")
        db.add_all([supervisor, agent, other_agent])
        db.flush()
        return supervisor, agent, other_agent

    def add_shift(self, db: Session, agent: User, work_date: date, available: bool = True):
        shift = AgentShift(
            agent_id=agent.id,
            work_date=work_date,
            region_code=REGION,
            is_available=available,
            shift_starts_at=local_instant(work_date, 8).astimezone(timezone.utc),
            shift_ends_at=local_instant(work_date, 17).astimezone(timezone.utc),
            start_latitude=14.6,
            start_longitude=121.1,
            max_visits=8,
            max_open_cases=20,
        )
        db.add(shift)
        db.flush()
        return shift

    def add_case(
        self,
        db: Session,
        supervisor: User,
        agent: User,
        reference: str,
        status: str,
        source: str = "manual",
        confirmed: bool = False,
        assignment_at: datetime | None = None,
    ):
        case = Investigation(
            reference_number=reference,
            first_name="Test",
            last_name="Subject",
            house_number="1",
            street="Test Road",
            region_code=REGION,
            status=status,
            assigned_agent_id=agent.id,
            latitude=14.65 if confirmed else None,
            longitude=121.05 if confirmed else None,
            location_source="manual" if confirmed else None,
            location_confirmed_at=datetime.now(timezone.utc) if confirmed else None,
            location_confirmed_by_id=supervisor.id if confirmed else None,
            h3_r7="r7" if confirmed else None,
            h3_r8="r8" if confirmed else None,
            h3_r9="r9" if confirmed else None,
        )
        db.add(case)
        db.flush()
        db.add(InvestigationAssignment(
            investigation_id=case.id,
            agent_id=agent.id,
            assigned_by_id=supervisor.id,
            assignment_source=source,
            assigned_at=assignment_at or datetime(2026, 11, 2, 8, tzinfo=timezone.utc),
        ))
        db.flush()
        return case

    def add_draft(self, db: Session, case: Investigation, agent: User, visited_at: datetime | None):
        report = InvestigationReport(
            investigation_id=case.id,
            author_id=agent.id,
            version=1,
            content="Field visit report",
            visit_outcome="visited",
            outcome="verified",
            verified_address="1 Test Road",
            visited_at=visited_at,
            status="draft",
        )
        db.add(report)
        db.flush()
        return report

    def test_shift_end_cancels_only_unfinished_work_once_and_stales_route(self):
        work_date = date(2026, 11, 2)
        with Session(self.engine) as db:
            supervisor, agent, _other = self.create_people(db)
            shift = self.add_shift(db, agent, work_date)
            unfinished = [
                self.add_case(db, supervisor, agent, f"INV-CANCEL-{status}", status)
                for status in ("pending", "assigned", "in_progress")
            ]
            under_review = self.add_case(db, supervisor, agent, "INV-SUBMITTED", "under_review")
            completed = self.add_case(db, supervisor, agent, "INV-COMPLETED", "completed")
            returned = self.add_case(db, supervisor, agent, "INV-RETURNED", "returned_for_correction")
            report = self.add_draft(db, unfinished[-1], agent, local_instant(work_date, 16).astimezone(timezone.utc))
            run = PlanningRun(
                requested_by_id=supervisor.id,
                auto_publish=True,
                work_date=work_date,
                region_code=REGION,
                investigation_ids=[unfinished[-1].id],
                agent_ids=[agent.id],
                locked_assignments=[],
                status="ready",
            )
            db.add(run)
            db.flush()
            shift.current_planning_run_id = run.id

            now = local_instant(work_date, 17, 1)
            first = process_shift_end_investigations(db, now)
            second = process_shift_end_investigations(db, now)

            self.assertEqual(first["cancelled"], 3)
            self.assertEqual(second["cancelled"], 0)
            for case in unfinished:
                self.assertEqual(case.status, "cancelled")
                self.assertEqual(case.reopen_on, work_date + timedelta(days=1))
            self.assertEqual(report.status, "draft")
            self.assertEqual(under_review.status, "under_review")
            self.assertEqual(completed.status, "completed")
            self.assertEqual(returned.status, "returned_for_correction")
            self.assertFalse(shift.is_available)
            self.assertIsNone(shift.current_planning_run_id)
            self.assertEqual(run.status, "stale")
            self.assertEqual(run.error_code, "shift_ended")
            self.assertEqual(
                db.query(ActivityLog).filter_by(action="investigation.cancelled_at_shift_end").count(),
                3,
            )

    def test_next_day_reopens_manual_and_releases_automatic_assignments(self):
        work_date = date(2026, 11, 2)
        next_date = work_date + timedelta(days=1)
        with Session(self.engine) as db:
            supervisor, agent, _other = self.create_people(db)
            old_shift = self.add_shift(db, agent, work_date)
            manual_case = self.add_case(db, supervisor, agent, "INV-MANUAL", "in_progress", "manual")
            automatic_case = self.add_case(db, supervisor, agent, "INV-AUTO", "assigned", "automatic")
            process_shift_end_investigations(db, local_instant(work_date, 17, 1))

            # There is no next-day shift: both cases reopen without a route or
            # a planning trigger, and the automatic assignment returns to VROOM.
            result = process_shift_end_investigations(db, local_instant(next_date, 7))

            self.assertEqual(result["reopened"], 2)
            self.assertEqual(manual_case.status, "pending")
            self.assertEqual(manual_case.reopen_on, None)
            self.assertEqual(manual_case.assigned_agent_id, agent.id)
            self.assertEqual(automatic_case.status, "pending")
            self.assertIsNone(automatic_case.reopen_on)
            self.assertIsNone(automatic_case.assigned_agent_id)
            auto_assignment = db.query(InvestigationAssignment).filter_by(
                investigation_id=automatic_case.id,
            ).one()
            self.assertFalse(auto_assignment.is_active)
            self.assertIsNotNone(auto_assignment.unassigned_at)
            self.assertEqual(result["planning_triggers"], 0)
            self.assertEqual(db.query(PlanningTrigger).count(), 0)
            self.assertEqual(old_shift.work_date, work_date)

    def test_reopened_cases_queue_once_when_a_next_day_shift_is_available(self):
        work_date = date(2026, 11, 2)
        next_date = work_date + timedelta(days=1)
        with Session(self.engine) as db:
            supervisor, agent, _other = self.create_people(db)
            self.add_shift(db, agent, work_date)
            case = self.add_case(db, supervisor, agent, "INV-REOPEN-QUEUE", "assigned", "automatic")
            self.add_shift(db, agent, next_date)

            result = process_shift_end_investigations(db, local_instant(next_date, 9))

            self.assertEqual(result["cancelled"], 1)
            self.assertEqual(result["reopened"], 1)
            self.assertEqual(result["planning_triggers"], 1)
            self.assertEqual(case.status, "pending")
            self.assertIsNone(case.assigned_agent_id)
            self.assertEqual(db.query(PlanningTrigger).count(), 1)
            trigger = db.query(PlanningTrigger).one()
            self.assertEqual(trigger.work_date, next_date)
            self.assertEqual(trigger.status, "pending")

    def test_previous_expiry_does_not_cancel_a_new_assignment_for_todays_shift(self):
        work_date = date(2026, 11, 2)
        next_date = work_date + timedelta(days=1)
        with Session(self.engine) as db:
            supervisor, agent, _other = self.create_people(db)
            old_shift = self.add_shift(db, agent, work_date)
            self.add_shift(db, agent, next_date)
            case = self.add_case(
                db,
                supervisor,
                agent,
                "INV-NEW-DAY-ASSIGNMENT",
                "assigned",
                "manual",
                assignment_at=local_instant(next_date, 9).astimezone(timezone.utc),
            )

            result = process_shift_end_investigations(db, local_instant(next_date, 10))

            self.assertEqual(result["cancelled"], 0)
            self.assertEqual(result["reopened"], 0)
            self.assertEqual(case.status, "assigned")
            self.assertIsNone(case.reopen_on)
            self.assertFalse(old_shift.is_available)

    def test_delayed_expiry_uses_each_assignment_shift_reopen_date(self):
        first_date = date(2026, 11, 2)
        second_date = first_date + timedelta(days=1)
        with Session(self.engine) as db:
            supervisor, agent, _other = self.create_people(db)
            self.add_shift(db, agent, first_date)
            self.add_shift(db, agent, second_date)
            first_case = self.add_case(
                db,
                supervisor,
                agent,
                "INV-DELAYED-FIRST-SHIFT",
                "assigned",
                assignment_at=local_instant(first_date, 9).astimezone(timezone.utc),
            )
            second_case = self.add_case(
                db,
                supervisor,
                agent,
                "INV-DELAYED-SECOND-SHIFT",
                "in_progress",
                assignment_at=local_instant(second_date, 9).astimezone(timezone.utc),
            )

            result = process_shift_end_investigations(db, local_instant(second_date, 17, 5))

            self.assertEqual(result["cancelled"], 2)
            # The first shift's next-day reopen date is already due when the
            # worker catches up, so it cancels and reopens in the same tick.
            self.assertEqual(first_case.status, "pending")
            self.assertIsNone(first_case.reopen_on)
            first_events = db.query(ActivityLog).filter_by(
                object_type="investigation",
                object_id=first_case.id,
            ).all()
            reopened_event = next(
                event for event in first_events
                if event.action == "investigation.reopened_after_shift"
            )
            self.assertEqual(reopened_event.details["previous_reopen_on"], second_date.isoformat())
            self.assertEqual(second_case.status, "cancelled")
            self.assertEqual(second_case.reopen_on, second_date + timedelta(days=1))

    def test_late_in_shift_report_supersedes_cancellation_before_reopen(self):
        work_date = date(2026, 11, 2)
        with Session(self.engine) as db:
            supervisor, agent, _other = self.create_people(db)
            shift = self.add_shift(db, agent, work_date)
            case = self.add_case(db, supervisor, agent, "INV-LATE-REPORT", "in_progress", confirmed=True)
            visited_at = local_instant(work_date, 16, 45).astimezone(timezone.utc)
            report = self.add_draft(db, case, agent, visited_at)
            process_shift_end_investigations(db, local_instant(work_date, 17, 1))

            submitted = submit_report(
                db,
                case,
                actor=agent,
                now=local_instant(work_date, 18),
            )

            self.assertEqual(submitted.status, "submitted")
            self.assertEqual(case.status, "under_review")
            self.assertIsNone(case.reopen_on)
            self.assertEqual(shift.last_completed_investigation_id, case.id)
            self.assertEqual(shift.last_completed_report_id, report.id)

    def test_late_report_outside_shift_or_after_reopen_is_rejected(self):
        work_date = date(2026, 11, 2)
        next_date = work_date + timedelta(days=1)
        with Session(self.engine) as db:
            supervisor, agent, _other = self.create_people(db)
            self.add_shift(db, agent, work_date)
            case = self.add_case(db, supervisor, agent, "INV-OUTSIDE-SHIFT", "in_progress")
            report = self.add_draft(
                db,
                case,
                agent,
                local_instant(work_date, 17, 30).astimezone(timezone.utc),
            )
            process_shift_end_investigations(db, local_instant(work_date, 18))
            with self.assertRaisesRegex(ValueError, "within the expired shift"):
                submit_report(db, case, actor=agent, now=local_instant(work_date, 19))
            db.rollback()

            # Delayed midnight processing still reopens from the saved date.
            process_shift_end_investigations(db, local_instant(next_date, 7))
            self.assertEqual(case.status, "pending")
            with self.assertRaises(ValueError):
                submit_report(db, case, actor=agent, now=local_instant(next_date, 8))
            self.assertEqual(report.status, "draft")

    def test_report_winning_the_expiry_race_is_left_under_review(self):
        work_date = date(2026, 11, 2)
        with Session(self.engine) as db:
            supervisor, agent, _other = self.create_people(db)
            self.add_shift(db, agent, work_date)
            case = self.add_case(db, supervisor, agent, "INV-REPORT-FIRST", "in_progress")
            report = self.add_draft(
                db,
                case,
                agent,
                local_instant(work_date, 16, 55).astimezone(timezone.utc),
            )

            submit_report(db, case, actor=agent, now=local_instant(work_date, 17, 2))
            result = process_shift_end_investigations(db, local_instant(work_date, 17, 2))

            self.assertEqual(report.status, "submitted")
            self.assertEqual(case.status, "under_review")
            self.assertIsNone(case.reopen_on)
            self.assertEqual(result["cancelled"], 0)

    def test_status_facets_and_agent_route_expose_reopen_date(self):
        work_date = date(2026, 11, 2)
        with Session(self.engine) as db:
            supervisor, agent, _other = self.create_people(db)
            self.add_shift(db, agent, work_date)
            case = self.add_case(db, supervisor, agent, "INV-STATUS-REOPEN", "assigned")
            process_shift_end_investigations(db, local_instant(work_date, 17, 1))

            page = get_investigations(db=db, current_user=supervisor, page=1, page_size=25)
            agent_route = published_agent_route(db, agent, work_date)
            map_data = planning_map_data(db, work_date)

            self.assertEqual(page["facets"]["status"]["cancelled"], 1)
            self.assertEqual(page["items"][0].status, "cancelled")
            self.assertEqual(page["items"][0].reopen_on, work_date + timedelta(days=1))
            self.assertEqual(agent_route["cancelled_investigations"][0]["id"], case.id)
            self.assertEqual(
                agent_route["cancelled_investigations"][0]["reopen_on"],
                work_date + timedelta(days=1),
            )
            AgentRouteResponse.model_validate(agent_route)
            map_response = PlanningMapDataResponse.model_validate(map_data)
            self.assertEqual(
                map_response.unlocated_investigations[0].reopen_on,
                work_date + timedelta(days=1),
            )


if __name__ == "__main__":
    unittest.main()
