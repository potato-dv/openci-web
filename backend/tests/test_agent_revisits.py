import unittest
from datetime import date, datetime, time, timedelta, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.database import Base
import app.models  # Register all tables before create_all.
from app.models import AgentRevisitRequest, AgentShift, Investigation, InvestigationReport, PlanningTrigger, User
from app.services.agent_revisits import activate_due_revisit_requests, request_agent_revisit
from app.services.agent_schedules import MANILA
from app.services.investigation import review_investigation_report, save_report_draft, submit_report
from app.schemas.report import ReportUpsert
from app.services.planning import _route_origin, planning_map_data


class AgentRevisitTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)

    def tearDown(self):
        self.engine.dispose()

    def make_case(self, db: Session, agent: User, status: str = "returned_for_correction"):
        case = Investigation(
            reference_number=f"INV-REVISIT-{datetime.now(timezone.utc).timestamp()}",
            first_name="Test",
            last_name="Subject",
            region_code="1300000000",
            latitude=14.65,
            longitude=121.05,
            location_source="manual",
            location_confirmed_at=datetime.now(timezone.utc),
            h3_r7="r7",
            h3_r8="r8",
            h3_r9="r9",
            status=status,
            assigned_agent_id=agent.id,
        )
        db.add(case)
        db.flush()
        return case

    def add_shift(self, db: Session, agent: User, work_date: date, starts_at: datetime, ends_at: datetime):
        shift = AgentShift(
            agent_id=agent.id,
            work_date=work_date,
            region_code="1300000000",
            is_available=True,
            shift_starts_at=starts_at,
            shift_ends_at=ends_at,
            start_latitude=14.6,
            start_longitude=121.1,
            max_visits=8,
            max_open_cases=20,
        )
        db.add(shift)
        db.flush()
        return shift

    def add_returned_report(self, db: Session, case: Investigation, agent: User):
        report = InvestigationReport(
            investigation_id=case.id,
            author_id=agent.id,
            version=1,
            content="Original submitted findings",
            visit_outcome="visited",
            outcome="verified",
            visited_at=datetime.now(timezone.utc),
            status="returned_for_correction",
        )
        db.add(report)
        db.flush()
        return report

    def test_submitted_location_is_visible_during_review_and_approval_keeps_it(self):
        with Session(self.engine) as db:
            agent = User(name="Agent", email="revisit-location@example.test", password="hash", role="agent")
            supervisor = User(name="Supervisor", email="revisit-review@example.test", password="hash", role="supervisor")
            db.add_all([agent, supervisor])
            db.flush()
            today = datetime.now(MANILA).date()
            shift = self.add_shift(
                db,
                agent,
                today,
                datetime.combine(today, time.min, MANILA).astimezone(timezone.utc),
                datetime.combine(today + timedelta(days=1), time.min, MANILA).astimezone(timezone.utc),
            )
            case = self.make_case(db, agent, status="in_progress")
            report = save_report_draft(
                db,
                case,
                agent,
                ReportUpsert(
                    content="Visit completed",
                    visit_outcome="visited",
                    outcome="verified",
                    verified_address="12 Example Street",
                    visited_at=datetime.now(timezone.utc) - timedelta(minutes=1),
                ),
            )

            submit_report(db, case)

            self.assertEqual(case.status, "under_review")
            self.assertEqual(shift.last_completed_investigation_id, case.id)
            self.assertEqual(shift.last_completed_report_id, report.id)
            self.assertEqual(
                _route_origin(shift)[0:2],
                (case.latitude, case.longitude),
            )
            agent_marker = next(item for item in planning_map_data(db, today)["agents"] if item["id"] == agent.id)
            self.assertEqual(agent_marker["start"]["label"], "Latest completed visit (estimated)")

            review_investigation_report(db, case, supervisor, "approved", None)

            self.assertEqual(case.status, "completed")
            self.assertEqual(shift.last_completed_investigation_id, case.id)
            self.assertEqual((shift.last_completed_latitude, shift.last_completed_longitude), (14.65, 121.05))

            concern = self.make_case(db, agent, status="in_progress")
            concern.latitude = 14.66
            concern.longitude = 121.06
            returned_visit_at = datetime.now(timezone.utc) - timedelta(seconds=10)
            save_report_draft(
                db,
                concern,
                agent,
                ReportUpsert(
                    content="Visit awaiting review",
                    visit_outcome="no_access",
                    outcome="inconclusive",
                    visited_at=returned_visit_at,
                ),
            )
            submit_report(db, concern)
            review_investigation_report(
                db,
                concern,
                supervisor,
                "returned_for_correction",
                "Please clarify the visit details.",
            )

            self.assertEqual(concern.status, "returned_for_correction")
            self.assertEqual((shift.last_completed_latitude, shift.last_completed_longitude), (14.66, 121.06))

    def test_revisit_waits_for_next_manual_shift_and_survives_session_restart(self):
        now = datetime.now(timezone.utc)
        today = now.astimezone(MANILA).date()
        next_day = today + timedelta(days=1)
        next_start = datetime.combine(next_day, time(8), MANILA).astimezone(timezone.utc)
        next_end = datetime.combine(next_day, time(17), MANILA).astimezone(timezone.utc)
        with Session(self.engine) as db:
            agent = User(name="Agent", email="revisit-next-shift@example.test", password="hash", role="agent")
            db.add(agent)
            db.flush()
            case = self.make_case(db, agent)
            report = self.add_returned_report(db, case, agent)
            self.add_shift(db, agent, next_day, next_start, next_end)

            request = request_agent_revisit(db, case, agent, now)
            returned_report_id = report.id
            db.commit()
            request_id = request.id
            self.assertEqual(request.status, "waiting_for_shift")
            self.assertEqual(request.target_work_date, next_day)
            self.assertEqual(case.status, "returned_for_correction")

        with Session(self.engine) as db:
            persisted = db.get(AgentRevisitRequest, request_id)
            self.assertEqual(persisted.report_id, returned_report_id)
            activation_now = datetime.combine(next_day, time(8, 5), MANILA).astimezone(timezone.utc)
            self.assertEqual(activate_due_revisit_requests(db, next_day, activation_now), 1)
            db.commit()
            self.assertEqual(persisted.status, "queued")
            self.assertEqual(db.get(Investigation, persisted.investigation_id).status, "assigned")

    def test_revisit_request_stays_pending_when_no_shift_is_configured(self):
        now = datetime.now(timezone.utc)
        today = now.astimezone(MANILA).date()
        with Session(self.engine) as db:
            agent = User(name="Agent", email="revisit-no-shift@example.test", password="hash", role="agent")
            db.add(agent)
            db.flush()
            case = self.make_case(db, agent)
            self.add_returned_report(db, case, agent)

            request = request_agent_revisit(db, case, agent, now)
            db.commit()

            self.assertEqual(request.status, "waiting_for_shift")
            self.assertIsNone(request.target_work_date)
            self.assertEqual(activate_due_revisit_requests(db, today + timedelta(days=1), now + timedelta(days=1)), 0)
            self.assertEqual(db.get(AgentRevisitRequest, request.id).status, "waiting_for_shift")

    def test_active_shift_revisit_is_queued_and_pre_shift_request_waits_until_start(self):
        now = datetime.now(timezone.utc)
        today = now.astimezone(MANILA).date()
        with Session(self.engine) as db:
            agent = User(name="Agent", email="revisit-active-shift@example.test", password="hash", role="agent")
            db.add(agent)
            db.flush()
            case = self.make_case(db, agent)
            self.add_returned_report(db, case, agent)
            self.add_shift(
                db,
                agent,
                today,
                datetime.combine(today, time.min, MANILA).astimezone(timezone.utc),
                datetime.combine(today + timedelta(days=1), time.min, MANILA).astimezone(timezone.utc),
            )

            request = request_agent_revisit(db, case, agent, now)

            self.assertEqual(request.status, "queued")
            self.assertEqual(request.target_work_date, today)
            self.assertEqual(case.status, "assigned")
            self.assertEqual(db.query(PlanningTrigger).filter_by(work_date=today).count(), 1)

            correction = save_report_draft(
                db,
                case,
                agent,
                ReportUpsert(
                    content="Revisit completed",
                    visit_outcome="visited",
                    outcome="verified",
                    verified_address="12 Example Street",
                    visited_at=now,
                ),
            )
            self.assertEqual(case.status, "assigned")
            with self.assertRaisesRegex(ValueError, "route to be published"):
                submit_report(db, case)
            request.status = "routed"
            with self.assertRaisesRegex(ValueError, "date and time of the requested revisit"):
                submit_report(db, case)
            correction = save_report_draft(
                db,
                case,
                agent,
                ReportUpsert(
                    content="Revisit completed",
                    visit_outcome="visited",
                    outcome="verified",
                    verified_address="12 Example Street",
                    visited_at=datetime.now(timezone.utc),
                ),
            )
            self.assertEqual(submit_report(db, case).id, correction.id)
            self.assertEqual(case.status, "under_review")
            self.assertEqual(request.status, "completed")
            shift = db.query(AgentShift).filter_by(agent_id=agent.id, work_date=today).one()
            self.assertEqual(shift.last_completed_investigation_id, case.id)

    def test_same_day_future_shift_is_not_queued_before_the_shift_starts(self):
        now = datetime.now(timezone.utc)
        today = now.astimezone(MANILA).date()
        local_now = now.astimezone(MANILA)
        shift_start = local_now + timedelta(hours=1)
        shift_end = datetime.combine(today + timedelta(days=1), time.min, MANILA)
        with Session(self.engine) as db:
            agent = User(name="Agent", email="revisit-later-shift@example.test", password="hash", role="agent")
            db.add(agent)
            db.flush()
            case = self.make_case(db, agent)
            self.add_returned_report(db, case, agent)
            self.add_shift(db, agent, today, shift_start.astimezone(timezone.utc), shift_end.astimezone(timezone.utc))

            request = request_agent_revisit(db, case, agent, now)

            self.assertEqual(request.status, "waiting_for_shift")
            self.assertEqual(request.target_work_date, today)
            self.assertEqual(case.status, "returned_for_correction")
            self.assertEqual(db.query(PlanningTrigger).filter_by(work_date=today).count(), 0)

            shift_start_utc = shift_start.astimezone(timezone.utc)
            self.assertEqual(
                activate_due_revisit_requests(db, today, shift_start_utc + timedelta(minutes=2)),
                1,
            )
            self.assertEqual(request.status, "queued")
            self.assertEqual(case.status, "assigned")


if __name__ == "__main__":
    unittest.main()
