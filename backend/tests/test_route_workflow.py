import unittest
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo
from unittest.mock import patch

from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.database import Base
import app.models  # Register every table before create_all.
from app.models import (
    AgentShift,
    Investigation,
    InvestigationAssignment,
    InvestigationReport,
    InvestigationRouteEvent,
    PlanningItem,
    PlanningRun,
    User,
)
from app.schemas.report import ReportUpsert
from app.schemas.route_event import UnableToProceedInput
from app.services.investigation import save_report_draft, submit_report
from app.services.route_workflow import (
    RouteActionConflict,
    cancel_investigation_for_no_contact,
    cancel_no_contact_event,
    finalize_no_contact_attempt,
    get_active_no_contact_event,
    record_unable_to_proceed,
    route_workflow_snapshot,
    start_current_investigation,
)


MANILA = ZoneInfo("Asia/Manila")
WORK_DATE = date(2026, 11, 5)
REGION = "1300000000"


def local_instant(hour: int, minute: int = 0) -> datetime:
    return datetime.combine(WORK_DATE, time(hour, minute), tzinfo=MANILA)


class RouteWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)

    def tearDown(self):
        self.engine.dispose()

    def seed_route(self, db: Session, count: int = 2):
        supervisor = User(name="Supervisor", email="route-supervisor@example.test", password="hash", role="supervisor")
        agent = User(name="Agent", email="route-agent@example.test", password="hash", role="agent")
        other = User(name="Other Agent", email="route-other@example.test", password="hash", role="agent")
        db.add_all([supervisor, agent, other])
        db.flush()
        shift = AgentShift(
            agent_id=agent.id,
            work_date=WORK_DATE,
            region_code=REGION,
            is_available=True,
            shift_starts_at=local_instant(8).astimezone(timezone.utc),
            shift_ends_at=local_instant(17).astimezone(timezone.utc),
            start_latitude=14.6,
            start_longitude=121.1,
            max_visits=8,
            max_open_cases=20,
        )
        db.add(shift)
        db.flush()

        cases = []
        for sequence in range(1, count + 1):
            case = Investigation(
                reference_number=f"INV-ROUTE-{sequence}",
                first_name="Taylor",
                last_name="Example",
                house_number=str(sequence),
                street="Sample Road",
                region_code=REGION,
                latitude=14.6 + sequence / 100,
                longitude=121.1 + sequence / 100,
                location_source="manual",
                location_confirmed_at=local_instant(7).astimezone(timezone.utc),
                location_confirmed_by_id=supervisor.id,
                h3_r7=f"r7-{sequence}",
                h3_r8=f"r8-{sequence}",
                h3_r9=f"r9-{sequence}",
                status="assigned",
                priority="normal",
                assigned_agent_id=agent.id,
                created_at=local_instant(7).astimezone(timezone.utc) - timedelta(minutes=sequence),
            )
            db.add(case)
            db.flush()
            db.add(InvestigationAssignment(
                investigation_id=case.id,
                agent_id=agent.id,
                assigned_by_id=supervisor.id,
                assignment_source="manual",
                assigned_at=local_instant(7).astimezone(timezone.utc) - timedelta(minutes=sequence),
            ))
            cases.append(case)
        db.flush()

        run = PlanningRun(
            requested_by_id=supervisor.id,
            auto_publish=True,
            work_date=WORK_DATE,
            region_code=REGION,
            investigation_ids=[case.id for case in cases],
            agent_ids=[agent.id],
            locked_assignments=[],
            status="applied",
            warnings=[],
            applied_at=local_instant(7).astimezone(timezone.utc),
        )
        db.add(run)
        db.flush()
        for sequence, case in enumerate(cases, start=1):
            db.add(PlanningItem(
                planning_run_id=run.id,
                investigation_id=case.id,
                agent_id=agent.id,
                outcome="assigned",
                sequence=sequence,
                planned_arrival_at=local_instant(9 + sequence),
            ))
        shift.current_planning_run_id = run.id
        db.commit()
        return supervisor, agent, other, shift, run, cases

    def test_backend_rejects_out_of_order_and_stale_route_actions(self):
        now = local_instant(9)
        with Session(self.engine) as db:
            _supervisor, agent, other, _shift, run, cases = self.seed_route(db)
            first, second = cases

            with self.assertRaisesRegex(RouteActionConflict, "out of sequence"):
                start_current_investigation(db, second.id, agent, WORK_DATE, run.id, now)
            with self.assertRaisesRegex(ValueError, "out of sequence"):
                save_report_draft(
                    db, second, agent, ReportUpsert(content="Out-of-order draft"),
                    route_revision=run.id, work_date=WORK_DATE,
                )
            with self.assertRaisesRegex(ValueError, "out of sequence"):
                submit_report(
                    db, second, actor=agent, route_revision=run.id,
                    work_date=WORK_DATE, now=now,
                )
            with self.assertRaisesRegex(RouteActionConflict, "no longer assigned"):
                start_current_investigation(db, first.id, other, WORK_DATE, run.id, now)
            with self.assertRaisesRegex(RouteActionConflict, "route changed"):
                start_current_investigation(db, first.id, agent, WORK_DATE, run.id + 1, now)
            with self.assertRaisesRegex(ValueError, "Start this current investigation"):
                save_report_draft(
                    db, first, agent, ReportUpsert(content="Not started"),
                    route_revision=run.id, work_date=WORK_DATE,
                )
            with self.assertRaisesRegex(ValueError, "Start this current investigation"):
                submit_report(
                    db, first, actor=agent, route_revision=run.id,
                    work_date=WORK_DATE, now=now,
                )
            self.assertEqual(db.query(InvestigationReport).count(), 0)

    def test_no_contact_deferral_unlocks_next_stop_without_creating_a_report(self):
        now = local_instant(9)
        with Session(self.engine) as db:
            _supervisor, agent, _other, _shift, run, cases = self.seed_route(db)
            first, second = cases
            start_current_investigation(db, first.id, agent, WORK_DATE, run.id, now)
            event = record_unable_to_proceed(
                db,
                first.id,
                agent,
                WORK_DATE,
                run.id,
                "requested_later_visit",
                "Contact asked us to return after lunch.",
                local_instant(13),
                local_instant(15),
                local_instant(9, 10),
            )

            state = route_workflow_snapshot(db, agent.id, WORK_DATE, local_instant(9, 11))
            self.assertEqual(state["current_actionable_investigation_id"], second.id)
            self.assertEqual(state["stop_states"][first.id]["sequence_state"], "deferred")
            self.assertEqual(event.event_type, "no_contact")
            self.assertEqual(event.state, "deferred")
            self.assertEqual(first.status, "assigned")
            self.assertEqual(db.query(InvestigationReport).count(), 0)
            self.assertEqual(db.query(InvestigationRouteEvent).count(), 1)

    def test_contact_window_allows_one_retry_then_finalizes_that_attempt_in_place(self):
        now = local_instant(9)
        with Session(self.engine) as db:
            _supervisor, agent, _other, shift, run, cases = self.seed_route(db)
            first, second = cases
            start_current_investigation(db, first.id, agent, WORK_DATE, run.id, now)
            original = record_unable_to_proceed(
                db,
                first.id,
                agent,
                WORK_DATE,
                run.id,
                "requested_later_visit",
                None,
                local_instant(13),
                local_instant(15),
                local_instant(9, 10),
            )
            start_current_investigation(db, second.id, agent, WORK_DATE, run.id, local_instant(9, 11))
            draft = save_report_draft(
                db,
                second,
                agent,
                ReportUpsert(
                    content="Visited the second location.",
                    visit_outcome="visited",
                    outcome="verified",
                    verified_address="2 Sample Road",
                    visited_at=local_instant(10).astimezone(timezone.utc),
                ),
                route_revision=run.id,
                work_date=WORK_DATE,
            )
            self.assertEqual(draft.status, "draft")
            submitted = submit_report(
                db,
                second,
                actor=agent,
                route_revision=run.id,
                work_date=WORK_DATE,
                now=local_instant(10, 30),
            )
            self.assertEqual(submitted.status, "submitted")
            self.assertEqual(second.status, "under_review")

            with patch("app.services.route_workflow._retry_feasible", return_value=True):
                too_early = route_workflow_snapshot(db, agent.id, WORK_DATE, local_instant(11))
                self.assertEqual(too_early["current_actionable_investigation_id"], first.id)
                self.assertFalse(too_early["can_start"])
                ready = route_workflow_snapshot(db, agent.id, WORK_DATE, local_instant(13))
                self.assertEqual(ready["current_actionable_kind"], "deferred_retry")
                self.assertTrue(ready["can_start"])
                start_current_investigation(db, first.id, agent, WORK_DATE, run.id, local_instant(13))
                retry = db.query(InvestigationRouteEvent).filter_by(
                    investigation_id=first.id,
                    retry_number=1,
                ).one()
                failed = record_unable_to_proceed(
                    db,
                    first.id,
                    agent,
                    WORK_DATE,
                    run.id,
                    "nobody_at_location",
                    None,
                    None,
                    None,
                    local_instant(13, 20),
                )

            self.assertEqual(original.state, "retry_failed")
            self.assertEqual(retry.state, "retry_failed")
            state = route_workflow_snapshot(db, agent.id, WORK_DATE, local_instant(13, 21))
            self.assertEqual(state["can_finalize_event"].id, retry.id)
            finalized = finalize_no_contact_attempt(
                db,
                failed.id,
                agent,
                WORK_DATE,
                run.id,
                local_instant(13, 22),
            )

            self.assertEqual(finalized.id, retry.id)
            self.assertEqual(finalized.state, "carried_over")
            self.assertEqual(original.state, "carried_over")
            self.assertEqual(finalized.next_work_date, WORK_DATE + timedelta(days=1))
            # The second (retry) attempt also failed, so the investigation is
            # cancelled until tomorrow instead of carried over indefinitely.
            # It is a manual assignment, so it keeps the same agent.
            self.assertEqual(first.status, "cancelled")
            self.assertEqual(first.reopen_on, WORK_DATE + timedelta(days=1))
            self.assertEqual(first.assigned_agent_id, agent.id)
            self.assertEqual(db.query(InvestigationReport).filter_by(investigation_id=first.id).count(), 0)
            self.assertEqual(db.query(InvestigationRouteEvent).filter_by(investigation_id=first.id).count(), 2)
            self.assertEqual(shift.last_attempted_investigation_id, first.id)

    def test_cancel_investigation_for_no_contact_releases_automatic_assignment(self):
        with Session(self.engine) as db:
            supervisor = User(name="Supervisor", email="cancel-helper-supervisor@example.test", password="hash", role="supervisor")
            agent = User(name="Agent", email="cancel-helper-agent@example.test", password="hash", role="agent")
            db.add_all([supervisor, agent])
            db.flush()
            case = Investigation(
                reference_number="INV-CANCEL-HELPER-AUTO",
                first_name="Taylor", last_name="Example",
                house_number="1", street="Sample Road", region_code=REGION,
                status="in_progress", priority="normal", assigned_agent_id=agent.id,
            )
            db.add(case)
            db.flush()
            assignment = InvestigationAssignment(
                investigation_id=case.id, agent_id=agent.id, assigned_by_id=supervisor.id,
                assignment_source="automatic",
            )
            db.add(assignment)
            event = InvestigationRouteEvent(
                investigation_id=case.id, agent_id=agent.id, work_date=WORK_DATE,
                event_type="no_contact", state="deferred", retry_number=0,
                reason="nobody_at_location", notes=None, attempted_at=local_instant(9),
            )
            db.add(event)
            db.commit()

            reopen_on = cancel_investigation_for_no_contact(
                db, case, event, WORK_DATE, local_instant(9, 5), agent.id,
                "investigation.cancelled_no_contact_finalized",
            )
            db.commit()

            self.assertEqual(reopen_on, WORK_DATE + timedelta(days=1))
            self.assertEqual(case.status, "cancelled")
            self.assertEqual(case.reopen_on, WORK_DATE + timedelta(days=1))
            self.assertIsNone(case.assigned_agent_id)
            self.assertFalse(assignment.is_active)
            self.assertIsNotNone(assignment.unassigned_at)
            self.assertEqual(event.state, "carried_over")
            self.assertEqual(event.next_work_date, WORK_DATE + timedelta(days=1))

    def test_cancel_no_contact_event_as_admin_before_a_second_attempt(self):
        with Session(self.engine) as db:
            _supervisor, agent, _other, _shift, run, cases = self.seed_route(db)
            first, _second = cases
            admin = User(name="Admin", email="cancel-admin@example.test", password="hash", role="admin")
            db.add(admin)
            db.flush()
            start_current_investigation(db, first.id, agent, WORK_DATE, run.id, local_instant(9))
            event = record_unable_to_proceed(
                db, first.id, agent, WORK_DATE, run.id,
                "nobody_at_location", None, None, None, local_instant(9, 5),
            )
            self.assertEqual(event.state, "deferred")
            self.assertEqual(get_active_no_contact_event(db, first.id).id, event.id)

            case = cancel_no_contact_event(db, first.id, event.id, admin, local_instant(9, 6))

            self.assertEqual(case.status, "cancelled")
            self.assertEqual(case.reopen_on, WORK_DATE + timedelta(days=1))
            self.assertEqual(case.assigned_agent_id, agent.id)
            self.assertEqual(event.state, "carried_over")
            self.assertIsNone(get_active_no_contact_event(db, first.id))

            with self.assertRaisesRegex(RouteActionConflict, "already finalized"):
                cancel_no_contact_event(db, first.id, event.id, admin, local_instant(9, 7))

    def test_other_reason_requires_a_note(self):
        with self.assertRaises(ValidationError):
            UnableToProceedInput(
                work_date=WORK_DATE,
                route_revision=1,
                reason="other",
            )

    def test_retry_feasibility_respects_contact_window_break_and_visit_deadline(self):
        from types import SimpleNamespace

        from app.services.route_workflow import _retry_feasible

        class Router:
            def __init__(self):
                self.client = SimpleNamespace(close=lambda: None)

            @staticmethod
            def table(_coordinates):
                return {"durations": [[0, 1800], [1800, 0]]}

        now = local_instant(10)
        shift = SimpleNamespace(
            work_date=WORK_DATE,
            is_available=True,
            shift_starts_at=local_instant(8),
            shift_ends_at=local_instant(17),
            break_starts_at=local_instant(12),
            break_ends_at=local_instant(13),
            last_completed_at=None,
            last_completed_latitude=None,
            last_completed_longitude=None,
            start_latitude=14.6,
            start_longitude=121.1,
        )
        case = SimpleNamespace(
            latitude=14.7,
            longitude=121.2,
            service_duration_seconds=3600,
            visit_not_before_at=None,
            visit_due_at=None,
        )
        event = SimpleNamespace(
            attempted_at=local_instant(9),
            latitude=14.6,
            longitude=121.1,
            contact_available_from=local_instant(13),
            contact_available_until=local_instant(14, 30),
        )

        with patch("app.services.routing.OSRMClient", Router):
            self.assertTrue(_retry_feasible(None, shift, case, event, now))
            event.contact_available_until = local_instant(13, 30)
            self.assertFalse(_retry_feasible(None, shift, case, event, now))
            event.contact_available_until = local_instant(14, 30)
            case.visit_due_at = local_instant(13, 45)
            self.assertFalse(_retry_feasible(None, shift, case, event, now))


if __name__ == "__main__":
    unittest.main()
