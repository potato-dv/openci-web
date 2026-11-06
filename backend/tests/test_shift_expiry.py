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
    AgentWeeklySchedule,
    AgentWorkProfile,
    Investigation,
    InvestigationAssignment,
    InvestigationReport,
    InvestigationRouteEvent,
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

    def test_shift_end_records_unvisited_work_without_changing_investigation_status(self):
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

            self.assertEqual(first["cancelled"], 0)
            self.assertEqual(first["carried_over"], 2)
            self.assertEqual(second["cancelled"], 0)
            self.assertEqual(second["carried_over"], 0)
            self.assertEqual([case.status for case in unfinished], ["pending", "assigned", "in_progress"])
            self.assertTrue(all(case.reopen_on is None for case in unfinished))
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
                0,
            )
            self.assertEqual(
                db.query(ActivityLog).filter_by(action="investigation.carried_over_at_shift_end").count(),
                2,
            )
            events = db.query(InvestigationRouteEvent).order_by(InvestigationRouteEvent.investigation_id).all()
            self.assertEqual(len(events), 2)
            self.assertTrue(all(event.event_type == "shift_end_not_visited" for event in events))
            self.assertTrue(all(event.state == "carried_over" for event in events))

    def test_shift_end_keeps_manual_owner_and_returns_automatic_work_to_pool(self):
        work_date = date(2026, 11, 2)
        next_date = date(2026, 11, 5)
        with Session(self.engine) as db:
            supervisor, agent, _other = self.create_people(db)
            old_shift = self.add_shift(db, agent, work_date)
            db.add(AgentWorkProfile(
                agent_id=agent.id,
                depot_latitude=14.6,
                depot_longitude=121.1,
            ))
            db.add(AgentWeeklySchedule(
                agent_id=agent.id,
                effective_from=work_date,
                enabled=True,
                region_code=REGION,
                max_visits=8,
                max_open_cases=20,
                days=[
                    {
                        "weekday": weekday,
                        "is_working": weekday == 3,
                        "shift_start": "08:00:00" if weekday == 3 else None,
                        "shift_end": "17:00:00" if weekday == 3 else None,
                        "break_start": None,
                        "break_end": None,
                    }
                    for weekday in range(7)
                ],
            ))
            manual_case = self.add_case(db, supervisor, agent, "INV-MANUAL", "assigned", "manual")
            automatic_case = self.add_case(db, supervisor, agent, "INV-AUTO", "assigned", "automatic")
            result = process_shift_end_investigations(db, local_instant(work_date, 17, 1))

            self.assertEqual(result["carried_over"], 2)
            self.assertEqual(result["reopened"], 0)
            self.assertEqual(manual_case.status, "assigned")
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
            self.assertEqual(result["planning_triggers"], 2)
            self.assertEqual(db.query(PlanningTrigger).count(), 2)
            triggers = sorted(trigger.work_date for trigger in db.query(PlanningTrigger).all())
            self.assertEqual(triggers, [work_date + timedelta(days=1), next_date])
            carry_events = {
                event.investigation_id: event
                for event in db.query(InvestigationRouteEvent).all()
            }
            self.assertEqual(carry_events[manual_case.id].next_work_date, next_date)
            self.assertEqual(carry_events[automatic_case.id].next_work_date, work_date + timedelta(days=1))
            self.assertEqual(old_shift.work_date, work_date)

    def test_shift_end_cancels_instead_of_carrying_over_a_single_no_contact_attempt(self):
        work_date = date(2026, 11, 2)
        reopen_on = work_date + timedelta(days=1)
        with Session(self.engine) as db:
            supervisor, agent, _other = self.create_people(db)
            self.add_shift(db, agent, work_date)
            case = self.add_case(db, supervisor, agent, "INV-NO-CONTACT-CARRY", "assigned")
            attempt = InvestigationRouteEvent(
                investigation_id=case.id,
                agent_id=agent.id,
                work_date=work_date,
                event_type="no_contact",
                state="deferred",
                retry_number=0,
                reason="requested_later_visit",
                notes=None,
                attempted_at=local_instant(work_date, 10).astimezone(timezone.utc),
                latitude=case.latitude,
                longitude=case.longitude,
            )
            db.add(attempt)
            db.flush()
            original_id = attempt.id

            result = process_shift_end_investigations(db, local_instant(work_date, 17, 1))

            self.assertEqual(result["cancelled"], 1)
            self.assertEqual(result["carried_over"], 0)
            self.assertEqual(db.query(InvestigationRouteEvent).count(), 1)
            self.assertEqual(attempt.id, original_id)
            self.assertEqual(attempt.event_type, "no_contact")
            self.assertEqual(attempt.state, "carried_over")
            finalized_at = attempt.finalized_at
            if finalized_at.tzinfo is None:
                finalized_at = finalized_at.replace(tzinfo=timezone.utc)
            self.assertEqual(finalized_at, local_instant(work_date, 17, 1).astimezone(timezone.utc))
            self.assertEqual(attempt.next_work_date, reopen_on)
            # Manual assignment keeps its agent, consistent with the other
            # cancellation trigger's existing reopen behavior.
            self.assertEqual(case.status, "cancelled")
            self.assertEqual(case.reopen_on, reopen_on)
            self.assertEqual(case.assigned_agent_id, agent.id)
            self.assertEqual(
                db.query(ActivityLog).filter_by(
                    action="investigation.cancelled_no_contact_shift_end",
                ).count(),
                1,
            )

    def test_shift_end_cancels_and_releases_automatic_assignment_after_single_attempt(self):
        work_date = date(2026, 11, 2)
        reopen_on = work_date + timedelta(days=1)
        with Session(self.engine) as db:
            supervisor, agent, _other = self.create_people(db)
            self.add_shift(db, agent, work_date)
            case = self.add_case(db, supervisor, agent, "INV-NO-CONTACT-AUTO", "assigned", "automatic")
            db.add(InvestigationRouteEvent(
                investigation_id=case.id,
                agent_id=agent.id,
                work_date=work_date,
                event_type="no_contact",
                state="deferred",
                retry_number=0,
                reason="nobody_at_location",
                notes=None,
                attempted_at=local_instant(work_date, 10).astimezone(timezone.utc),
                latitude=case.latitude,
                longitude=case.longitude,
            ))
            db.flush()

            result = process_shift_end_investigations(db, local_instant(work_date, 17, 1))

            self.assertEqual(result["cancelled"], 1)
            self.assertEqual(case.status, "cancelled")
            self.assertEqual(case.reopen_on, reopen_on)
            self.assertIsNone(case.assigned_agent_id)
            assignment = db.query(InvestigationAssignment).filter_by(investigation_id=case.id).one()
            self.assertFalse(assignment.is_active)
            self.assertIsNotNone(assignment.unassigned_at)

    def test_shift_end_cancels_manual_assignment_after_a_failed_retry(self):
        work_date = date(2026, 11, 2)
        reopen_on = work_date + timedelta(days=1)
        with Session(self.engine) as db:
            supervisor, agent, _other = self.create_people(db)
            self.add_shift(db, agent, work_date)
            case = self.add_case(db, supervisor, agent, "INV-NO-CONTACT-RETRY-FAILED", "assigned")
            root = InvestigationRouteEvent(
                investigation_id=case.id,
                agent_id=agent.id,
                work_date=work_date,
                event_type="no_contact",
                state="retry_failed",
                retry_number=0,
                reason="requested_later_visit",
                notes=None,
                attempted_at=local_instant(work_date, 9).astimezone(timezone.utc),
                latitude=case.latitude,
                longitude=case.longitude,
            )
            db.add(root)
            db.flush()
            child = InvestigationRouteEvent(
                investigation_id=case.id,
                agent_id=agent.id,
                work_date=work_date,
                parent_event_id=root.id,
                event_type="no_contact",
                state="retry_failed",
                retry_number=1,
                reason="no_contact_person",
                notes=None,
                attempted_at=local_instant(work_date, 14).astimezone(timezone.utc),
                latitude=case.latitude,
                longitude=case.longitude,
            )
            db.add(child)
            db.flush()

            result = process_shift_end_investigations(db, local_instant(work_date, 17, 1))

            self.assertEqual(result["cancelled"], 1)
            self.assertEqual(case.status, "cancelled")
            self.assertEqual(case.reopen_on, reopen_on)
            self.assertEqual(case.assigned_agent_id, agent.id)
            self.assertEqual(root.state, "carried_over")
            self.assertEqual(child.state, "carried_over")
            self.assertEqual(root.next_work_date, reopen_on)
            self.assertEqual(child.next_work_date, reopen_on)

    def test_no_contact_cancellation_reopens_to_pending_and_requeues_planning_next_day(self):
        work_date = date(2026, 11, 2)
        next_date = work_date + timedelta(days=1)
        with Session(self.engine) as db:
            supervisor, agent, _other = self.create_people(db)
            self.add_shift(db, agent, work_date)
            automatic_case = self.add_case(db, supervisor, agent, "INV-REOPEN-AUTO", "assigned", "automatic")
            manual_case = self.add_case(db, supervisor, agent, "INV-REOPEN-MANUAL", "assigned", "manual")
            for case in (automatic_case, manual_case):
                db.add(InvestigationRouteEvent(
                    investigation_id=case.id,
                    agent_id=agent.id,
                    work_date=work_date,
                    event_type="no_contact",
                    state="deferred",
                    retry_number=0,
                    reason="nobody_at_location",
                    notes=None,
                    attempted_at=local_instant(work_date, 10).astimezone(timezone.utc),
                    latitude=case.latitude,
                    longitude=case.longitude,
                ))
            db.flush()

            day_one = process_shift_end_investigations(db, local_instant(work_date, 17, 1))
            self.assertEqual(day_one["cancelled"], 2)
            self.assertEqual(automatic_case.status, "cancelled")
            self.assertEqual(manual_case.status, "cancelled")

            self.add_shift(db, agent, next_date)
            day_two = process_shift_end_investigations(db, local_instant(next_date, 9))

            self.assertEqual(day_two["reopened"], 2)
            self.assertEqual(automatic_case.status, "pending")
            self.assertEqual(manual_case.status, "pending")
            self.assertIsNone(automatic_case.reopen_on)
            self.assertIsNone(manual_case.reopen_on)
            self.assertIsNone(automatic_case.assigned_agent_id)
            self.assertEqual(manual_case.assigned_agent_id, agent.id)
            triggers = db.query(PlanningTrigger).filter_by(work_date=next_date).all()
            self.assertGreaterEqual(len(triggers), 1)

    def test_automatic_carryover_queues_once_for_the_next_planning_day(self):
        work_date = date(2026, 11, 2)
        next_date = work_date + timedelta(days=1)
        with Session(self.engine) as db:
            supervisor, agent, _other = self.create_people(db)
            self.add_shift(db, agent, work_date)
            case = self.add_case(db, supervisor, agent, "INV-REOPEN-QUEUE", "assigned", "automatic")
            self.add_shift(db, agent, next_date)

            result = process_shift_end_investigations(db, local_instant(next_date, 9))

            self.assertEqual(result["cancelled"], 0)
            self.assertEqual(result["carried_over"], 1)
            self.assertEqual(result["reopened"], 0)
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
            self.assertEqual(db.query(InvestigationRouteEvent).count(), 0)

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

            self.assertEqual(result["cancelled"], 0)
            self.assertEqual(result["carried_over"], 2)
            self.assertEqual(first_case.status, "assigned")
            self.assertIsNone(first_case.reopen_on)
            self.assertEqual(second_case.status, "in_progress")
            self.assertIsNone(second_case.reopen_on)

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

    def test_pending_manual_assignment_can_submit_only_a_past_visit_on_the_same_manila_day(self):
        work_date = date(2026, 11, 4)
        now = local_instant(work_date, 11, 4)
        with Session(self.engine) as db:
            supervisor, agent, _other = self.create_people(db)
            self.add_shift(db, agent, work_date)
            case = self.add_case(db, supervisor, agent, "INV-PENDING-MANUAL-REPORT", "pending")
            report = self.add_draft(
                db,
                case,
                agent,
                local_instant(work_date, 11, 30).astimezone(timezone.utc),
            )

            with self.assertRaisesRegex(ValueError, "cannot be in the future"):
                submit_report(db, case, actor=agent, now=now)
            self.assertEqual(report.status, "draft")
            self.assertEqual(case.status, "pending")

            report.visited_at = local_instant(work_date, 10, 30).astimezone(timezone.utc)
            submitted = submit_report(db, case, actor=agent, now=now)
            self.assertEqual(submitted.status, "submitted")
            self.assertEqual(case.status, "under_review")

            other_case = self.add_case(db, supervisor, agent, "INV-OLD-DAY-REPORT", "pending")
            self.add_draft(
                db,
                other_case,
                agent,
                local_instant(work_date - timedelta(days=1), 10, 30).astimezone(timezone.utc),
            )
            with self.assertRaisesRegex(ValueError, "Manila workday when the visit occurred"):
                submit_report(db, other_case, actor=agent, now=now)

    def test_active_visit_survives_shift_end_and_report_must_record_in_shift_visit_time(self):
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
            self.assertEqual(case.status, "in_progress")
            self.assertEqual(db.query(InvestigationRouteEvent).count(), 0)
            with self.assertRaisesRegex(ValueError, "within the agent shift"):
                submit_report(db, case, actor=agent, now=local_instant(work_date, 19))
            db.rollback()

            # An active visit can still be submitted after shift end when its
            # recorded field visit happened during the shift.
            report.visited_at = local_instant(work_date, 16, 45).astimezone(timezone.utc)
            submitted = submit_report(db, case, actor=agent, now=local_instant(work_date, 19))
            self.assertEqual(submitted.status, "submitted")
            self.assertEqual(case.status, "under_review")

            process_shift_end_investigations(db, local_instant(next_date, 7))
            self.assertEqual(case.status, "under_review")
            self.assertEqual(report.status, "submitted")

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

            self.assertEqual(page["facets"]["status"]["cancelled"], 0)
            self.assertEqual(page["items"][0].status, "assigned")
            self.assertIsNone(page["items"][0].reopen_on)
            self.assertEqual(agent_route["cancelled_investigations"], [])
            self.assertEqual(agent_route["deferred_attempts"][0]["investigation_id"], case.id)
            self.assertEqual(agent_route["deferred_attempts"][0]["event_type"], "shift_end_not_visited")
            AgentRouteResponse.model_validate(agent_route)
            map_response = PlanningMapDataResponse.model_validate(map_data)
            self.assertEqual(
                map_response.unlocated_investigations[0].reopen_on,
                None,
            )


if __name__ == "__main__":
    unittest.main()
