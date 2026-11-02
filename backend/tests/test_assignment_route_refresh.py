import unittest
from datetime import datetime, time, timedelta, timezone
from unittest.mock import patch
from zoneinfo import ZoneInfo

from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.database import Base
from app.models.assignment import InvestigationAssignment
from app.models.investigation import Investigation
from app.models.planning import AgentShift, PlanningItem, PlanningRoute, PlanningRun
from app.models.user import User
from app.schemas.assignment import AssignmentCreate, AssignmentResponse
from app.schemas.planning import (
    LocationConfirm,
    LockedAssignment,
    PlanningRouteOverviewResponse,
    PlanningRunCreate,
)
from app.services.geospatial import cells_for_point
from app.services.investigation import assign_investigation
from app.services.planning import (
    apply_run,
    create_run,
    execute_run,
    planning_route_overview,
    queue_automatic_planning,
    queue_shift_route_refresh,
    reconcile_missing_route_scopes,
    sync_assignment_route_refresh,
    _link_auto_route_run,
    _digest,
    _snapshot,
)
from app.controllers.investigation import assign
from app.routes.investigation import confirm_investigation_location, retry_investigation_route_refresh
from app.workers.tasks import _sync_auto_route_assignments, optimize_planning_run


REGION = "1300000000"


def _work_date():
    return datetime.now(ZoneInfo("Asia/Manila")).date()


def _case(reference: str, supervisor_id: int, agent_id: int | None = None):
    cells = cells_for_point(14.5, 121.0)
    return Investigation(
        reference_number=reference,
        first_name="Fictional",
        last_name="Case",
        house_number="10",
        street="Test Road",
        region_code=REGION,
        status="assigned" if agent_id else "pending",
        priority="normal",
        assigned_agent_id=agent_id,
        latitude=14.5,
        longitude=121.0,
        location_source="manual",
        location_confirmed_at=datetime.now(timezone.utc),
        location_confirmed_by_id=supervisor_id,
        h3_r7=cells["h3_r7"],
        h3_r8=cells["h3_r8"],
        h3_r9=cells["h3_r9"],
    )


def _shift(agent_id: int, region_code: str = REGION, available: bool = True):
    work_date = _work_date()
    manila = ZoneInfo("Asia/Manila")
    start = datetime.combine(work_date, time(8), tzinfo=manila).astimezone(timezone.utc)
    end = datetime.combine(work_date, time(17), tzinfo=manila).astimezone(timezone.utc)
    return AgentShift(
        agent_id=agent_id,
        work_date=work_date,
        region_code=region_code,
        is_available=available,
        shift_starts_at=start,
        shift_ends_at=end,
        start_latitude=14.6,
        start_longitude=121.1,
        max_visits=10,
        max_open_cases=30,
    )


def _planning_clock(work_date: date, local_time: time = time(8)):
    fixed_now = datetime.combine(work_date, local_time, tzinfo=ZoneInfo("Asia/Manila"))

    class FrozenDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return fixed_now.astimezone(tz) if tz else fixed_now.replace(tzinfo=None)

    return patch("app.services.planning.datetime", FrozenDateTime)


class AssignmentRouteRefreshTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)

    def tearDown(self):
        self.engine.dispose()

    def _users(self, db):
        supervisor = User(name="Supervisor", email="route-supervisor@example.test", password="hash", role="supervisor")
        first_agent = User(name="First Agent", email="route-agent-one@example.test", password="hash", role="agent")
        second_agent = User(name="Second Agent", email="route-agent-two@example.test", password="hash", role="agent")
        db.add_all([supervisor, first_agent, second_agent])
        db.flush()
        return supervisor, first_agent, second_agent

    def test_late_active_shift_plans_from_assumed_depot_without_past_departure(self):
        with Session(self.engine) as db:
            supervisor, agent, _second = self._users(db)
            work_date = _work_date()
            case = _case("INV-LATE-SHIFT-PLAN", supervisor.id, agent.id)
            shift = _shift(agent.id, "ALL")
            shift.break_starts_at = datetime.combine(work_date, time(12), tzinfo=ZoneInfo("Asia/Manila")).astimezone(timezone.utc)
            shift.break_ends_at = datetime.combine(work_date, time(13), tzinfo=ZoneInfo("Asia/Manila")).astimezone(timezone.utc)
            db.add_all([case, shift])
            db.flush()
            assignment = InvestigationAssignment(
                investigation_id=case.id,
                agent_id=agent.id,
                assigned_by_id=supervisor.id,
                assignment_source="manual",
            )
            db.add(assignment)
            db.flush()
            run = create_run(
                db,
                PlanningRunCreate(
                    work_date=work_date,
                    region_code="ALL",
                    investigation_ids=[case.id],
                    agent_ids=[agent.id],
                    locked_assignments=[LockedAssignment(investigation_id=case.id, agent_id=agent.id)],
                ),
                supervisor,
            )
            run_id = run.id
            case_id = case.id
            agent_id = agent.id
            shift_start = shift.shift_starts_at
            depot_latitude = shift.start_latitude
            depot_longitude = shift.start_longitude

        departure = datetime.combine(work_date, time(10), tzinfo=ZoneInfo("Asia/Manila"))
        departure_epoch = int(departure.timestamp())
        break_arrival = int(datetime.combine(work_date, time(11, 55), tzinfo=ZoneInfo("Asia/Manila")).timestamp())
        end_arrival = int(datetime.combine(work_date, time(13, 10), tzinfo=ZoneInfo("Asia/Manila")).timestamp())

        class Router:
            @staticmethod
            def nearest_many(coordinates):
                return [{"distance": 10} for _ in coordinates]

            @staticmethod
            def table(coordinates):
                size = len(coordinates)
                return {
                    "durations": [[0 if i == j else 600 for j in range(size)] for i in range(size)],
                    "distances": [[0 if i == j else 5000 for j in range(size)] for i in range(size)],
                }

            @staticmethod
            def route(coordinates):
                return {
                    "geometry": {"type": "LineString", "coordinates": [[lon, lat] for lat, lon in coordinates]},
                    "distance": 5000,
                    "duration": 3900,
                }

            @staticmethod
            def close():
                pass

        class Solver:
            payload = None

            def solve(self, payload):
                Solver.payload = payload
                return {
                    "routes": [{
                        "vehicle": agent_id,
                        "steps": [
                            {"type": "start", "arrival": departure_epoch},
                            {"type": "job", "id": case_id, "arrival": departure_epoch + 600},
                            {"type": "break", "arrival": break_arrival, "waiting_time": 300, "service": 3600},
                            {"type": "end", "arrival": end_arrival},
                        ],
                    }],
                    "unassigned": [],
                }

            @staticmethod
            def close():
                pass

        with Session(self.engine) as db, _planning_clock(work_date, time(10)), \
                patch("app.services.planning.OSRMClient", Router), patch("app.services.planning.VROOMClient", Solver):
            execute_run(db, run_id)
            run = db.get(PlanningRun, run_id)
            item = db.query(PlanningItem).filter_by(planning_run_id=run_id, investigation_id=case_id).one()
            route = db.query(PlanningRoute).filter_by(planning_run_id=run_id, agent_id=agent_id).one()

            self.assertEqual(run.status, "ready")
            self.assertEqual(item.outcome, "assigned")
            self.assertEqual(item.agent_id, agent_id)
            vehicle = Solver.payload["vehicles"][0]
            self.assertEqual(vehicle["start"], [depot_longitude, depot_latitude])
            self.assertEqual(vehicle["time_window"][0], departure_epoch)
            self.assertGreaterEqual(vehicle["time_window"][0], int(shift_start.timestamp()))
            self.assertIn("assumed; no live location available", route.start["label"])

    def test_agent_with_in_progress_visit_is_preserved_and_reported_as_blocked(self):
        with Session(self.engine) as db:
            supervisor, agent, _second = self._users(db)
            work_date = _work_date()
            in_progress = _case("INV-IN-PROGRESS-KEEP", supervisor.id, agent.id)
            in_progress.status = "in_progress"
            pending = _case("INV-WAIT-FOR-IN-PROGRESS", supervisor.id)
            shift = _shift(agent.id)
            db.add_all([in_progress, pending, shift])
            db.flush()
            assignment = InvestigationAssignment(
                investigation_id=in_progress.id,
                agent_id=agent.id,
                assigned_by_id=supervisor.id,
                assignment_source="manual",
            )
            db.add(assignment)
            run = create_run(
                db,
                PlanningRunCreate(
                    work_date=work_date,
                    region_code=REGION,
                    investigation_ids=[pending.id],
                    agent_ids=[agent.id],
                ),
                supervisor,
            )
            run_id = run.id
            pending_id = pending.id
            in_progress_id = in_progress.id
            agent_id = agent.id

        class Router:
            @staticmethod
            def close():
                pass

        class Solver:
            @staticmethod
            def close():
                pass

        with Session(self.engine) as db, _planning_clock(work_date, time(10)), \
                patch("app.services.planning.OSRMClient", return_value=Router()), \
                patch("app.services.planning.VROOMClient", return_value=Solver()):
            execute_run(db, run_id)
            run = db.get(PlanningRun, run_id)
            item = db.query(PlanningItem).filter_by(planning_run_id=run_id, investigation_id=pending_id).one()
            current_visit = db.get(Investigation, in_progress_id)

            self.assertEqual(run.status, "ready")
            self.assertEqual(item.outcome, "unassigned")
            self.assertEqual(item.reason, "agent_in_progress")
            self.assertEqual(current_visit.status, "in_progress")
            self.assertEqual(current_visit.assigned_agent_id, agent_id)

    def test_background_applied_run_cannot_claim_published_without_current_route(self):
        with Session(self.engine) as db:
            supervisor, agent, _second = self._users(db)
            case = _case("INV-APPLIED-WITHOUT-ROUTE", supervisor.id, agent.id)
            shift = _shift(agent.id)
            db.add_all([case, shift])
            db.flush()
            assignment = InvestigationAssignment(
                investigation_id=case.id,
                agent_id=agent.id,
                assigned_by_id=supervisor.id,
                assignment_source="manual",
                auto_route_status="published",
                auto_route_work_date=_work_date(),
            )
            db.add(assignment)
            db.flush()
            run = PlanningRun(
                requested_by_id=supervisor.id,
                work_date=_work_date(),
                region_code=REGION,
                investigation_ids=[case.id],
                agent_ids=[agent.id],
                locked_assignments=[{"investigation_id": case.id, "agent_id": agent.id}],
                status="queued",
                auto_publish=True,
            )
            db.add(run)
            db.flush()
            _link_auto_route_run(db, run)
            db.add(PlanningItem(
                planning_run_id=run.id,
                investigation_id=case.id,
                agent_id=None,
                outcome="unassigned",
                reason="no_available_agents",
            ))
            run.status = "applied"
            db.commit()

            _sync_auto_route_assignments(db, run)

            db.refresh(assignment)
            self.assertEqual(assignment.auto_route_status, "failed")
            self.assertIn("no_available_agents", assignment.auto_route_errors)
            self.assertEqual(assignment.auto_route_run_ids, [run.id])

    def test_reconciliation_recovers_multiple_existing_assignments_once_and_preserves_them(self):
        with Session(self.engine) as db:
            supervisor, first_agent, second_agent = self._users(db)
            first_case = _case("INV-RECOVERY-ONE", supervisor.id, first_agent.id)
            second_case = _case("INV-RECOVERY-TWO", supervisor.id, second_agent.id)
            blocked_case = _case("INV-RECOVERY-BLOCKED", supervisor.id, second_agent.id)
            blocked_case.latitude = None
            blocked_case.longitude = None
            blocked_case.location_source = None
            blocked_case.location_confirmed_at = None
            blocked_case.h3_r7 = None
            blocked_case.h3_r8 = None
            blocked_case.h3_r9 = None
            unassigned_case = _case("INV-RECOVERY-UNASSIGNED", supervisor.id)
            db.add_all([
                first_case,
                second_case,
                blocked_case,
                unassigned_case,
                _shift(first_agent.id),
                _shift(second_agent.id),
            ])
            db.flush()
            assignments = [
                InvestigationAssignment(
                    investigation_id=case.id,
                    agent_id=case.assigned_agent_id,
                    assigned_by_id=supervisor.id,
                )
                for case in (first_case, second_case, blocked_case)
            ]
            db.add_all(assignments)
            db.commit()
            original_agent_ids = {
                case.id: case.assigned_agent_id
                for case in (first_case, second_case, blocked_case)
            }

            with patch("app.workers.tasks.optimize_planning_run.apply_async") as dispatch:
                first_summary = reconcile_missing_route_scopes(db, _work_date())
                second_summary = reconcile_missing_route_scopes(db, _work_date())

            run = db.query(PlanningRun).filter_by(auto_publish=True).one()
            self.assertEqual(first_summary["scopes_queued_or_coalesced"], 1)
            self.assertEqual(second_summary["scopes_queued_or_coalesced"], 1)
            self.assertEqual(dispatch.call_count, 1)
            self.assertEqual(set(run.investigation_ids), {first_case.id, second_case.id})
            self.assertEqual(
                {item["investigation_id"]: item["agent_id"] for item in run.locked_assignments},
                {first_case.id: first_agent.id, second_case.id: second_agent.id},
            )
            self.assertEqual(
                {case.id: case.assigned_agent_id for case in (first_case, second_case, blocked_case)},
                original_agent_ids,
            )
            self.assertIsNone(unassigned_case.assigned_agent_id)
            self.assertEqual(
                {warning["investigation_id"] for warning in run.warnings},
                {blocked_case.id},
            )
            self.assertTrue(all(assignment.is_active for assignment in assignments))

    def test_reconciliation_offers_automatic_day_off_assignments_to_working_agents(self):
        with Session(self.engine) as db:
            supervisor, off_agent, working_agent = self._users(db)
            automatic_case = _case("INV-DAY-OFF-AUTO", supervisor.id, off_agent.id)
            manual_case = _case("INV-DAY-OFF-MANUAL", supervisor.id, off_agent.id)
            db.add_all([automatic_case, manual_case, _shift(working_agent.id)])
            db.flush()
            automatic_assignment = InvestigationAssignment(
                investigation_id=automatic_case.id,
                agent_id=off_agent.id,
                assigned_by_id=supervisor.id,
                assignment_source="automatic",
            )
            manual_assignment = InvestigationAssignment(
                investigation_id=manual_case.id,
                agent_id=off_agent.id,
                assigned_by_id=supervisor.id,
                assignment_source="manual",
            )
            db.add_all([automatic_assignment, manual_assignment])
            db.commit()

            with patch("app.workers.tasks.optimize_planning_run.apply_async") as dispatch:
                summary = reconcile_missing_route_scopes(db, _work_date())

            run = db.query(PlanningRun).filter_by(auto_publish=True).one()
            self.assertEqual(summary["scopes_queued_or_coalesced"], 1)
            self.assertEqual(dispatch.call_count, 1)
            self.assertEqual(run.investigation_ids, [automatic_case.id])
            self.assertEqual(run.movable_investigation_ids, [automatic_case.id])
            self.assertEqual(run.agent_ids, [working_agent.id])
            self.assertEqual(automatic_case.assigned_agent_id, off_agent.id)
            self.assertTrue(automatic_assignment.is_active)
            self.assertEqual(manual_case.assigned_agent_id, off_agent.id)
            self.assertTrue(manual_assignment.is_active)

    def test_capacity_overflow_stales_a_queued_partial_run(self):
        with Session(self.engine) as db:
            supervisor, agent, _second = self._users(db)
            cases = [_case(f"INV-CAPACITY-{index:03d}", supervisor.id) for index in range(81)]
            db.add_all([_shift(agent.id), cases[0]])
            db.commit()

            with patch("app.workers.tasks.optimize_planning_run.apply_async") as dispatch:
                first = queue_automatic_planning(db, REGION, supervisor, _work_date())
                db.add_all(cases[1:])
                db.commit()
                overflow = queue_automatic_planning(db, REGION, supervisor, _work_date())

            db.refresh(first)
            self.assertEqual(first.status, "stale")
            self.assertEqual(first.error_code, "planning_scope_capacity_exceeded")
            self.assertEqual(overflow.status, "failed")
            self.assertEqual(overflow.error_code, "planning_scope_capacity_exceeded")
            self.assertEqual(len(overflow.investigation_ids), 81)
            self.assertEqual(dispatch.call_count, 1)

    def test_reconciliation_skips_invalid_only_assignment_and_permanent_failure(self):
        with Session(self.engine) as db:
            supervisor, agent, _second = self._users(db)
            invalid_case = _case("INV-RECOVERY-INVALID", supervisor.id, agent.id)
            invalid_case.latitude = None
            invalid_case.longitude = None
            invalid_case.location_source = None
            invalid_case.location_confirmed_at = None
            invalid_case.h3_r7 = None
            invalid_case.h3_r8 = None
            invalid_case.h3_r9 = None
            db.add_all([invalid_case, _shift(agent.id)])
            db.flush()
            db.add(InvestigationAssignment(
                investigation_id=invalid_case.id,
                agent_id=agent.id,
                assigned_by_id=supervisor.id,
            ))
            db.commit()
            with patch("app.workers.tasks.optimize_planning_run.apply_async") as dispatch:
                summary = reconcile_missing_route_scopes(db, _work_date())
            self.assertEqual(summary["scopes_queued_or_coalesced"], 0)
            self.assertEqual(db.query(PlanningRun).count(), 0)
            dispatch.assert_not_called()

            valid_case = _case("INV-RECOVERY-PERMANENT", supervisor.id, agent.id)
            shift = db.query(AgentShift).filter_by(
                agent_id=agent.id,
                work_date=_work_date(),
            ).one()
            db.add(valid_case)
            db.flush()
            permanent = PlanningRun(
                requested_by_id=supervisor.id,
                work_date=_work_date(),
                region_code=REGION,
                investigation_ids=[valid_case.id],
                agent_ids=[agent.id],
                locked_assignments=[{"investigation_id": valid_case.id, "agent_id": agent.id}],
                status="failed",
                error_code="planning_scope_capacity_exceeded",
                auto_publish=True,
                finished_at=datetime.now(timezone.utc) - timedelta(hours=1),
            )
            db.add(permanent)
            db.flush()
            permanent.input_digest = _digest(_snapshot(
                db,
                permanent,
                [valid_case],
                [shift],
                [agent],
            ))
            db.commit()
            with patch("app.workers.tasks.optimize_planning_run.apply_async") as dispatch:
                summary = reconcile_missing_route_scopes(db, _work_date())
            self.assertEqual(summary["scopes_with_permanent_failures"], 1)
            self.assertEqual(db.query(PlanningRun).count(), 1)
            dispatch.assert_not_called()

            valid_case.service_duration_seconds += 60
            db.commit()
            with patch("app.workers.tasks.optimize_planning_run.apply_async") as dispatch:
                changed = reconcile_missing_route_scopes(db, _work_date())
            self.assertEqual(changed["scopes_queued_or_coalesced"], 1)
            self.assertEqual(db.query(PlanningRun).count(), 2)
            dispatch.assert_called_once()

    def test_reconciliation_retries_schedule_failure_without_expired_unassigned_candidates(self):
        with Session(self.engine) as db:
            supervisor, agent, _second = self._users(db)
            case = _case("INV-RECOVERY-TRANSIENT", supervisor.id, agent.id)
            expired_unassigned_case = _case("INV-RECOVERY-EXPIRED-CANDIDATE", supervisor.id)
            expired_unassigned_case.visit_not_before_at = datetime.now(timezone.utc) - timedelta(hours=2)
            expired_unassigned_case.visit_due_at = datetime.now(timezone.utc) - timedelta(minutes=30)
            shift = _shift(agent.id)
            db.add_all([case, expired_unassigned_case, shift])
            db.flush()
            failed = PlanningRun(
                requested_by_id=supervisor.id,
                work_date=_work_date(),
                region_code=REGION,
                investigation_ids=[case.id, expired_unassigned_case.id],
                agent_ids=[agent.id],
                locked_assignments=[{"investigation_id": case.id, "agent_id": agent.id}],
                status="failed",
                error_code="vroom_solution_schedule_invalid",
                auto_publish=True,
                finished_at=datetime.now(timezone.utc),
            )
            db.add(failed)
            db.flush()
            failed.input_digest = _digest(_snapshot(
                db,
                failed,
                [case, expired_unassigned_case],
                [shift],
                [agent],
            ))
            db.commit()

            with patch("app.workers.tasks.optimize_planning_run.apply_async") as dispatch:
                waiting = reconcile_missing_route_scopes(db, _work_date())
                self.assertEqual(waiting["scopes_in_backoff"], 1)
                self.assertEqual(db.query(PlanningRun).count(), 1)
                dispatch.assert_not_called()

                failed.finished_at = datetime.now(timezone.utc) - timedelta(minutes=6)
                db.commit()
                retried = reconcile_missing_route_scopes(db, _work_date())

            self.assertEqual(retried["scopes_queued_or_coalesced"], 1)
            self.assertEqual(db.query(PlanningRun).count(), 2)
            self.assertEqual(dispatch.call_count, 1)
            queued = db.query(PlanningRun).filter(PlanningRun.id != failed.id).one()
            self.assertEqual(queued.status, "queued")
            self.assertEqual(queued.investigation_ids, [case.id])

    def test_reconciliation_retries_prior_planner_failures_after_logic_version_changes(self):
        with Session(self.engine) as db:
            supervisor, agent, _second = self._users(db)
            case = _case("INV-RECOVERY-OLD-PLANNER", supervisor.id, agent.id)
            shift = _shift(agent.id)
            db.add_all([case, shift])
            db.flush()
            db.add(InvestigationAssignment(
                investigation_id=case.id,
                agent_id=agent.id,
                assigned_by_id=supervisor.id,
                assignment_source="manual",
            ))
            failed = PlanningRun(
                requested_by_id=supervisor.id,
                work_date=_work_date(),
                region_code=REGION,
                investigation_ids=[case.id],
                agent_ids=[agent.id],
                locked_assignments=[{"investigation_id": case.id, "agent_id": agent.id}],
                status="failed",
                error_code="vroom_solution_schedule_invalid",
                auto_publish=True,
                finished_at=datetime.now(timezone.utc),
            )
            db.add(failed)
            db.flush()
            old_snapshot = _snapshot(db, failed, [case], [shift], [agent])
            old_snapshot.pop("planner_logic_version")
            failed.input_digest = _digest(old_snapshot)
            db.commit()

            with patch("app.workers.tasks.optimize_planning_run.apply_async") as dispatch:
                summary = reconcile_missing_route_scopes(db, _work_date())

            self.assertEqual(summary["scopes_queued_or_coalesced"], 1)
            self.assertEqual(summary["scopes_in_backoff"], 0)
            self.assertEqual(dispatch.call_count, 1)
            queued = db.query(PlanningRun).filter(PlanningRun.id != failed.id).one()
            self.assertEqual(queued.status, "queued")
            self.assertEqual(queued.investigation_ids, [case.id])

    def test_old_logic_failures_do_not_exhaust_retries_for_current_logic(self):
        with Session(self.engine) as db:
            supervisor, agent, _second = self._users(db)
            case = _case("INV-RECOVERY-RETRY-VERSION", supervisor.id, agent.id)
            shift = _shift(agent.id)
            db.add_all([case, shift])
            db.flush()
            db.add(InvestigationAssignment(
                investigation_id=case.id,
                agent_id=agent.id,
                assigned_by_id=supervisor.id,
                assignment_source="manual",
            ))
            now = datetime.now(timezone.utc)
            old_runs = []
            for attempt in range(3):
                failed = PlanningRun(
                    requested_by_id=supervisor.id,
                    work_date=_work_date(),
                    region_code=REGION,
                    investigation_ids=[case.id],
                    agent_ids=[agent.id],
                    locked_assignments=[{"investigation_id": case.id, "agent_id": agent.id}],
                    status="failed",
                    error_code="vroom_solution_schedule_invalid",
                    auto_publish=True,
                    created_at=now - timedelta(minutes=12 - attempt),
                    finished_at=now - timedelta(minutes=12 - attempt),
                )
                db.add(failed)
                db.flush()
                old_snapshot = _snapshot(db, failed, [case], [shift], [agent])
                old_snapshot.pop("planner_logic_version")
                failed.input_digest = _digest(old_snapshot)
                old_runs.append(failed)

            current = PlanningRun(
                requested_by_id=supervisor.id,
                work_date=_work_date(),
                region_code=REGION,
                investigation_ids=[case.id],
                agent_ids=[agent.id],
                locked_assignments=[{"investigation_id": case.id, "agent_id": agent.id}],
                status="failed",
                error_code="vroom_solution_schedule_invalid",
                auto_publish=True,
                created_at=now - timedelta(minutes=6),
                finished_at=now - timedelta(minutes=6),
            )
            db.add(current)
            db.flush()
            current.input_digest = _digest(_snapshot(db, current, [case], [shift], [agent]))
            db.commit()

            with patch("app.workers.tasks.optimize_planning_run.apply_async") as dispatch:
                summary = reconcile_missing_route_scopes(db, _work_date())

            self.assertEqual(summary["scopes_queued_or_coalesced"], 1)
            self.assertEqual(summary["scopes_at_retry_limit"], 0)
            self.assertEqual(dispatch.call_count, 1)

    def test_direct_assignment_queues_locked_same_day_work_and_same_agent_repeat_is_idempotent(self):
        with Session(self.engine) as db:
            supervisor, agent, _second = self._users(db)
            prior_case = _case("INV-AUTO-PRIOR", supervisor.id, agent.id)
            db.add(prior_case)
            db.flush()
            db.add(InvestigationAssignment(
                investigation_id=prior_case.id,
                agent_id=agent.id,
                assigned_by_id=supervisor.id,
            ))
            current_case = _case("INV-AUTO-NEW", supervisor.id)
            old_run = PlanningRun(
                requested_by_id=supervisor.id,
                work_date=_work_date(),
                region_code=REGION,
                investigation_ids=[prior_case.id],
                agent_ids=[agent.id],
                locked_assignments=[{"investigation_id": prior_case.id, "agent_id": agent.id}],
                status="applied",
                auto_publish=True,
            )
            shift = _shift(agent.id)
            db.add_all([current_case, shift, old_run])
            db.flush()
            shift.current_planning_run_id = old_run.id
            db.commit()
            case_id = current_case.id

            with patch("app.workers.tasks.optimize_planning_run.apply_async") as queue:
                assignment = assign(db, case_id, AssignmentCreate(agent_id=agent.id), supervisor)
                run = db.query(PlanningRun).filter_by(auto_assignment_id=assignment.id).one()
                self.assertEqual(assignment.auto_route_status, "queued")
                self.assertEqual(assignment.auto_route_work_date, _work_date())
                response = AssignmentResponse.model_validate(assignment)
                self.assertEqual(response.route_refresh.status, "queued")
                self.assertTrue(run.auto_publish)
                # The former route pointer remains intact until a fully
                # validated replacement is atomically published.
                self.assertEqual(
                    db.query(AgentShift).filter_by(agent_id=agent.id, work_date=_work_date()).one().current_planning_run_id,
                    old_run.id,
                )
                self.assertEqual(set(run.investigation_ids), {prior_case.id, case_id})
                self.assertEqual(
                    {item["investigation_id"]: item["agent_id"] for item in run.locked_assignments},
                    {prior_case.id: agent.id, case_id: agent.id},
                )
                self.assertEqual(queue.call_count, 1)

                repeated = assign(db, case_id, AssignmentCreate(agent_id=agent.id, note="Updated note"), supervisor)
                self.assertEqual(repeated.id, assignment.id)
                self.assertEqual(db.query(PlanningRun).count(), 2)
                self.assertEqual(
                    db.query(PlanningRun)
                    .filter(PlanningRun.auto_assignment_id.is_not(None))
                    .count(),
                    1,
                )
                self.assertEqual(queue.call_count, 1)

    def test_reassignment_rebuilds_remaining_former_agent_work_without_redistribution(self):
        with Session(self.engine) as db:
            supervisor, former_agent, new_agent = self._users(db)
            reassigned_case = _case("INV-AUTO-MOVED", supervisor.id, former_agent.id)
            remaining_case = _case("INV-AUTO-REMAINING", supervisor.id, former_agent.id)
            db.add_all([reassigned_case, remaining_case])
            db.flush()
            assignment = InvestigationAssignment(
                investigation_id=reassigned_case.id,
                agent_id=former_agent.id,
                assigned_by_id=supervisor.id,
            )
            remaining_assignment = InvestigationAssignment(
                investigation_id=remaining_case.id,
                agent_id=former_agent.id,
                assigned_by_id=supervisor.id,
            )
            db.add_all([assignment, remaining_assignment, _shift(former_agent.id), _shift(new_agent.id)])
            db.commit()

            with patch("app.workers.tasks.optimize_planning_run.apply_async") as queue:
                updated = assign(db, reassigned_case.id, AssignmentCreate(agent_id=new_agent.id), supervisor)
                self.assertEqual(updated.auto_route_agent_ids, [former_agent.id, new_agent.id])
                run = db.query(PlanningRun).filter_by(auto_assignment_id=updated.id).one()
                self.assertEqual(set(run.agent_ids), {former_agent.id, new_agent.id})
                self.assertEqual(set(run.investigation_ids), {reassigned_case.id, remaining_case.id})
                locked = {item["investigation_id"]: item["agent_id"] for item in run.locked_assignments}
                self.assertEqual(locked, {
                    reassigned_case.id: new_agent.id,
                    remaining_case.id: former_agent.id,
                })
                self.assertEqual(queue.call_count, 1)
                self.assertFalse(db.get(InvestigationAssignment, assignment.id).is_active)
                self.assertTrue(db.get(InvestigationAssignment, remaining_assignment.id).is_active)

    def test_today_shift_change_requeues_existing_assigned_work(self):
        with Session(self.engine) as db:
            supervisor, agent, _second = self._users(db)
            case = _case("INV-AUTO-SHIFT", supervisor.id, agent.id)
            db.add(case)
            db.flush()
            assignment = InvestigationAssignment(
                investigation_id=case.id,
                agent_id=agent.id,
                assigned_by_id=supervisor.id,
            )
            db.add_all([assignment, _shift(agent.id)])
            db.commit()

            with patch("app.workers.tasks.optimize_planning_run.apply_async") as queue:
                refreshed = queue_shift_route_refresh(db, agent.id, _work_date(), supervisor)
                self.assertEqual(refreshed.status, "queued")
                run = db.query(PlanningRun).filter_by(
                    work_date=_work_date(), region_code=REGION, auto_publish=True
                ).one()
                self.assertEqual(run.investigation_ids, [case.id])
                self.assertEqual(run.agent_ids, [agent.id])
                self.assertEqual(run.auto_assignment_id, None)
                overview = planning_route_overview(db, _work_date(), REGION)
                self.assertEqual(overview["agents"][0]["route_status"], "queued")
                queue.assert_called_once_with(args=[run.id], countdown=3)

    def test_legacy_same_agent_assignment_queues_route_despite_unrelated_blockers(self):
        with Session(self.engine) as db:
            supervisor, agent, _second = self._users(db)
            valid_case = _case("INV-LEGACY-VALID", supervisor.id, agent.id)
            unlocated_case = Investigation(
                reference_number="INV-LEGACY-UNLOCATED",
                first_name="Fictional",
                last_name="Case",
                region_code=REGION,
                status="assigned",
                priority="normal",
                assigned_agent_id=agent.id,
            )
            other_region_case = _case("INV-LEGACY-OTHER-REGION", supervisor.id, agent.id)
            other_region_case.region_code = "0400000000"
            db.add_all([valid_case, unlocated_case, other_region_case, _shift(agent.id)])
            db.flush()
            assignments = [
                InvestigationAssignment(
                    investigation_id=case.id,
                    agent_id=agent.id,
                    assigned_by_id=supervisor.id,
                    assignment_source="manual",
                )
                for case in (valid_case, unlocated_case, other_region_case)
            ]
            db.add_all(assignments)
            db.commit()

            with _planning_clock(_work_date()), patch("app.workers.tasks.optimize_planning_run.apply_async") as queue:
                refreshed = assign(
                    db,
                    valid_case.id,
                    AssignmentCreate(agent_id=agent.id),
                    supervisor,
                )

            run = db.query(PlanningRun).filter_by(auto_assignment_id=assignments[0].id).one()
            self.assertEqual(refreshed.auto_route_status, "queued")
            self.assertEqual(run.agent_ids, [agent.id])
            self.assertEqual(run.investigation_ids, [valid_case.id])
            self.assertEqual(
                run.locked_assignments,
                [{"investigation_id": valid_case.id, "agent_id": agent.id}],
            )
            self.assertEqual(
                {(warning["investigation_id"], warning["reason"]) for warning in run.warnings},
                {
                    (unlocated_case.id, "location_unconfirmed"),
                    (other_region_case.id, "region_mismatch"),
                },
            )
            self.assertEqual(
                [db.get(Investigation, case.id).assigned_agent_id for case in (valid_case, unlocated_case, other_region_case)],
                [agent.id, agent.id, agent.id],
            )
            queue.assert_called_once_with(args=[run.id], countdown=3)

            shift = db.query(AgentShift).filter_by(
                agent_id=agent.id,
                work_date=_work_date(),
            ).one()
            start_epoch = int(shift.shift_starts_at.replace(tzinfo=timezone.utc).timestamp())

            class Router:
                @staticmethod
                def nearest_many(coordinates):
                    return [{"distance": 10} for _ in coordinates]

                @staticmethod
                def table(coordinates):
                    size = len(coordinates)
                    return {
                        "durations": [[0 if i == j else 600 for j in range(size)] for i in range(size)],
                        "distances": [[0 if i == j else 5000 for j in range(size)] for i in range(size)],
                    }

                @staticmethod
                def route(coordinates):
                    return {
                        "geometry": {"type": "LineString", "coordinates": [[lon, lat] for lat, lon in coordinates]},
                        "distance": 5000,
                        "duration": 3900,
                    }

                @staticmethod
                def close():
                    pass

            class Solver:
                def solve(self, payload):
                    return {
                        "routes": [{
                            "vehicle": agent.id,
                            "steps": [
                                {"type": "start", "arrival": start_epoch},
                                {"type": "job", "id": valid_case.id, "arrival": start_epoch + 600},
                                {"type": "end", "arrival": start_epoch + 3900},
                            ],
                        }],
                        "unassigned": [],
                    }

                @staticmethod
                def close():
                    pass

            with _planning_clock(_work_date()), patch("app.services.planning.OSRMClient", Router), patch(
                "app.services.planning.VROOMClient", Solver
            ):
                execute_run(db, run.id)

            self.assertEqual(db.get(PlanningRun, run.id).status, "ready")
            self.assertEqual(
                {(warning["investigation_id"], warning["reason"]) for warning in db.get(PlanningRun, run.id).warnings},
                {
                    (unlocated_case.id, "location_unconfirmed"),
                    (other_region_case.id, "region_mismatch"),
                },
            )
            with _planning_clock(_work_date()):
                apply_run(db, run.id, db.get(PlanningRun, run.id).result_digest, supervisor)
            sync_assignment_route_refresh(db, assignments[0].id)
            overview = planning_route_overview(db, _work_date(), REGION)
            agent_route = overview["agents"][0]
            self.assertEqual(agent_route["route_status"], "partially_published")
            self.assertEqual([stop["investigation_id"] for stop in agent_route["stops"]], [valid_case.id])

    def test_overview_publishes_valid_stop_and_explains_blocked_assignments(self):
        with Session(self.engine) as db:
            supervisor, agent, _second = self._users(db)
            valid_case = _case("INV-OVERVIEW-VALID", supervisor.id, agent.id)
            unlocated_case = Investigation(
                reference_number="INV-OVERVIEW-UNLOCATED",
                first_name="Fictional",
                last_name="Case",
                region_code=REGION,
                status="assigned",
                priority="normal",
                assigned_agent_id=agent.id,
            )
            other_region_case = _case("INV-OVERVIEW-OTHER-REGION", supervisor.id, agent.id)
            other_region_case.region_code = "0400000000"
            shift = _shift(agent.id)
            db.add_all([valid_case, unlocated_case, other_region_case, shift])
            db.flush()
            db.add_all([
                InvestigationAssignment(investigation_id=case.id, agent_id=agent.id, assigned_by_id=supervisor.id)
                for case in (valid_case, unlocated_case, other_region_case)
            ])
            run = PlanningRun(
                requested_by_id=supervisor.id,
                work_date=_work_date(),
                region_code=REGION,
                investigation_ids=[valid_case.id],
                agent_ids=[agent.id],
                locked_assignments=[{"investigation_id": valid_case.id, "agent_id": agent.id}],
                status="applied",
                auto_publish=True,
            )
            db.add(run)
            db.flush()
            shift.current_planning_run_id = run.id
            geometry = {"type": "LineString", "coordinates": [[121.1, 14.6], [121.0, 14.5]]}
            db.add_all([
                PlanningItem(
                    planning_run_id=run.id,
                    investigation_id=valid_case.id,
                    agent_id=agent.id,
                    outcome="assigned",
                    sequence=1,
                ),
                PlanningRoute(
                    planning_run_id=run.id,
                    agent_id=agent.id,
                    geometry_status="ready",
                    geometry=geometry,
                    geometry_digest=_digest(geometry),
                    start={"latitude": 14.6, "longitude": 121.1},
                ),
            ])
            db.commit()

            overview = planning_route_overview(db, _work_date(), REGION)
            agent_route = overview["agents"][0]

            self.assertEqual(agent_route["route_status"], "partially_published")
            self.assertEqual([stop["investigation_id"] for stop in agent_route["stops"]], [valid_case.id])
            self.assertEqual(
                {(warning["investigation_id"], warning["reason"]) for warning in agent_route["planning_warnings"]},
                {
                    (unlocated_case.id, "location_unconfirmed"),
                    (other_region_case.id, "region_mismatch"),
                },
            )
            response = PlanningRouteOverviewResponse.model_validate(overview)
            self.assertEqual(response.agents[0].planning_warnings[0].reason, "location_unconfirmed")

    def test_shift_added_during_active_empty_roster_run_requests_replan(self):
        with Session(self.engine) as db:
            supervisor, agent, _second = self._users(db)
            case = _case("INV-AUTO-SHIFT-ADDED", supervisor.id)
            db.add(case)
            db.flush()
            run = PlanningRun(
                requested_by_id=supervisor.id,
                work_date=_work_date(),
                region_code=REGION,
                investigation_ids=[case.id],
                agent_ids=[],
                locked_assignments=[],
                status="running",
                auto_publish=True,
            )
            db.add_all([run, _shift(agent.id)])
            db.commit()
            run_id = run.id

            with patch("app.workers.tasks.optimize_planning_run.apply_async"):
                refreshed = queue_automatic_planning(
                    db, REGION, supervisor, _work_date()
                )

            self.assertEqual(refreshed.id, run_id)
            self.assertEqual(refreshed.agent_ids, [])
            self.assertTrue(refreshed.auto_replan_requested)

    def test_assignment_lock_change_during_active_run_requests_replan(self):
        with Session(self.engine) as db:
            supervisor, agent, _second = self._users(db)
            case = _case("INV-AUTO-LOCK-CHANGED", supervisor.id, agent.id)
            db.add(case)
            db.flush()
            run = PlanningRun(
                requested_by_id=supervisor.id,
                work_date=_work_date(),
                region_code=REGION,
                investigation_ids=[case.id],
                agent_ids=[agent.id],
                locked_assignments=[],
                status="running",
                auto_publish=True,
            )
            db.add_all([_shift(agent.id), run])
            db.commit()

            refreshed = queue_automatic_planning(db, REGION, supervisor, _work_date())

            self.assertEqual(refreshed.id, run.id)
            self.assertTrue(refreshed.auto_replan_requested)

    def test_case_input_change_during_active_run_requests_replan(self):
        with Session(self.engine) as db:
            supervisor, agent, _second = self._users(db)
            case = _case("INV-AUTO-INPUT-CHANGED", supervisor.id, agent.id)
            shift = _shift(agent.id)
            db.add_all([case, shift])
            db.flush()
            run = create_run(
                db,
                PlanningRunCreate(
                    work_date=_work_date(),
                    region_code=REGION,
                    investigation_ids=[case.id],
                    agent_ids=[agent.id],
                    locked_assignments=[
                        LockedAssignment(investigation_id=case.id, agent_id=agent.id)
                    ],
                ),
                supervisor,
            )
            run.status = "running"
            run.auto_publish = True
            db.commit()
            case.service_duration_seconds += 600
            db.commit()

            refreshed = queue_automatic_planning(db, REGION, supervisor, _work_date())

            self.assertEqual(refreshed.id, run.id)
            self.assertTrue(refreshed.auto_replan_requested)

    def test_missing_shift_rejects_manual_override_without_creating_assignment(self):
        with Session(self.engine) as db:
            supervisor, agent, _second = self._users(db)
            case = _case("INV-AUTO-NO-SHIFT", supervisor.id)
            db.add(case)
            db.commit()

            with patch("app.workers.tasks.optimize_planning_run.apply_async") as queue:
                with self.assertRaises(HTTPException) as raised:
                    assign(db, case.id, AssignmentCreate(agent_id=agent.id), supervisor)
            self.assertEqual(raised.exception.status_code, 409)
            self.assertIsNone(db.get(Investigation, case.id).assigned_agent_id)
            self.assertEqual(db.query(InvestigationAssignment).filter_by(investigation_id=case.id).count(), 0)
            self.assertEqual(queue.call_count, 0)
            self.assertEqual(db.query(PlanningRun).count(), 0)

    def test_location_confirmation_queues_automatic_planning_once(self):
        with Session(self.engine) as db:
            supervisor, agent, _second = self._users(db)
            case = Investigation(
                reference_number="INV-AUTO-CONFIRM",
                first_name="Fictional",
                last_name="Case",
                region_code=REGION,
                status="pending",
                priority="normal",
            )
            db.add_all([case, _shift(agent.id)])
            db.commit()
            case_id = case.id

            with patch("app.workers.tasks.optimize_planning_run.apply_async") as queue:
                confirmed = confirm_investigation_location(
                    case_id,
                    LocationConfirm(latitude=14.5, longitude=121.0, source="manual"),
                    db,
                    supervisor,
                )
                self.assertTrue(confirmed.location_confirmed)
                run = db.query(PlanningRun).filter_by(auto_publish=True).one()
                self.assertEqual(run.investigation_ids, [case_id])
                self.assertEqual(run.agent_ids, [agent.id])
                self.assertEqual(run.status, "queued")

                # A repeated confirmation of the same point does not enqueue
                # duplicate automatic work.
                confirm_investigation_location(
                    case_id,
                    LocationConfirm(latitude=14.5, longitude=121.0, source="manual"),
                    db,
                    supervisor,
                )
                self.assertEqual(db.query(PlanningRun).count(), 1)
                self.assertEqual(queue.call_count, 1)

    def test_retry_endpoint_requeues_the_active_assignment(self):
        with Session(self.engine) as db:
            supervisor, agent, _second = self._users(db)
            case = _case("INV-AUTO-RETRY", supervisor.id, agent.id)
            db.add(case)
            db.flush()
            assignment = InvestigationAssignment(
                investigation_id=case.id,
                agent_id=agent.id,
                assigned_by_id=supervisor.id,
                auto_route_status="failed",
                auto_route_work_date=_work_date(),
                auto_route_agent_ids=[agent.id],
                auto_route_run_ids=[],
                auto_route_errors=["agent_shift_unavailable_today"],
            )
            db.add_all([assignment, _shift(agent.id)])
            db.commit()

            with patch("app.workers.tasks.optimize_planning_run.apply_async") as queue:
                retried = retry_investigation_route_refresh(case.id, db, supervisor)

            self.assertEqual(retried.id, assignment.id)
            self.assertEqual(retried.auto_route_status, "queued")
            self.assertEqual(len(retried.auto_route_run_ids), 1)
            self.assertEqual(queue.call_count, 1)

    def test_automatic_worker_publishes_only_a_complete_valid_route(self):
        with Session(self.engine) as db:
            supervisor, agent, _second = self._users(db)
            agent_id = agent.id
            case = _case("INV-AUTO-PUBLISH", supervisor.id, agent.id)
            db.add(case)
            db.flush()
            assignment = InvestigationAssignment(
                investigation_id=case.id,
                agent_id=agent.id,
                assigned_by_id=supervisor.id,
                auto_route_status="queued",
                auto_route_work_date=_work_date(),
                auto_route_agent_ids=[agent.id],
                auto_route_run_ids=[],
                auto_route_errors=[],
            )
            shift = _shift(agent.id)
            db.add_all([assignment, shift])
            db.flush()
            run = create_run(
                db,
                PlanningRunCreate(
                    work_date=_work_date(),
                    region_code=REGION,
                    investigation_ids=[case.id],
                    agent_ids=[agent.id],
                    locked_assignments=[LockedAssignment(investigation_id=case.id, agent_id=agent.id)],
                ),
                supervisor,
            )
            run.auto_publish = True
            run.auto_assignment_id = assignment.id
            assignment.auto_route_run_ids = [run.id]
            shift_start = shift.shift_starts_at
            db.commit()
            run_id = run.id
            assignment_id = assignment.id

        def make_session():
            return Session(self.engine)

        def make_ready(db, run_id):
            run = db.get(PlanningRun, run_id)
            run.status = "ready"
            run.result_digest = "ready-result"
            db.add(PlanningItem(
                planning_run_id=run.id,
                investigation_id=run.investigation_ids[0],
                agent_id=agent_id,
                outcome="assigned",
                sequence=1,
                estimated_arrival_at=shift_start + timedelta(minutes=10),
                travel_seconds=600,
                travel_metres=5000,
            ))
            from app.services.planning import _digest

            geometry = {"type": "LineString", "coordinates": [[121.1, 14.6], [121.0, 14.5]]}
            db.add(PlanningRoute(
                planning_run_id=run.id,
                agent_id=agent_id,
                geometry_status="ready",
                geometry=geometry,
                geometry_digest=_digest(geometry),
                start={"latitude": 14.6, "longitude": 121.1},
            ))
            db.commit()

        try:
            with _planning_clock(_work_date()), \
                    patch("app.workers.tasks.SessionLocal", side_effect=make_session), patch(
                        "app.workers.tasks.execute_run", side_effect=make_ready
                    ):
                result = optimize_planning_run.run(run_id)
            self.assertEqual(result["status"], "applied")
            with Session(self.engine) as db:
                run = db.get(PlanningRun, run_id)
                assignment = db.get(InvestigationAssignment, assignment_id)
                shift = db.query(AgentShift).filter_by(agent_id=agent_id, work_date=_work_date()).one()
                self.assertTrue(run.auto_publish)
                self.assertEqual(run.status, "applied")
                self.assertEqual(shift.current_planning_run_id, run_id)
                self.assertEqual(assignment.auto_route_status, "published")
        finally:
            self.engine.dispose()

    def test_automatic_worker_does_not_publish_without_valid_road_geometry(self):
        with Session(self.engine) as db:
            supervisor, agent, _second = self._users(db)
            case = _case("INV-AUTO-NO-GEOMETRY", supervisor.id, agent.id)
            db.add(case)
            db.flush()
            assignment = InvestigationAssignment(
                investigation_id=case.id,
                agent_id=agent.id,
                assigned_by_id=supervisor.id,
                auto_route_status="queued",
                auto_route_work_date=_work_date(),
                auto_route_agent_ids=[agent.id],
                auto_route_run_ids=[],
                auto_route_errors=[],
            )
            shift = _shift(agent.id)
            db.add_all([assignment, shift])
            db.flush()
            run = PlanningRun(
                requested_by_id=supervisor.id,
                work_date=_work_date(),
                region_code=REGION,
                investigation_ids=[case.id],
                agent_ids=[agent.id],
                locked_assignments=[{"investigation_id": case.id, "agent_id": agent.id}],
                status="queued",
                auto_publish=True,
                auto_assignment_id=assignment.id,
            )
            db.add(run)
            db.flush()
            assignment.auto_route_run_ids = [run.id]
            db.commit()
            run_id = run.id
            assignment_id = assignment.id
            agent_id = agent.id

        def make_session():
            return Session(self.engine)

        def make_ready_without_geometry(db, run_id):
            run = db.get(PlanningRun, run_id)
            run.status = "ready"
            run.result_digest = "ready-result"
            db.add(PlanningItem(
                planning_run_id=run.id,
                investigation_id=run.investigation_ids[0],
                agent_id=agent_id,
                outcome="assigned",
                sequence=1,
            ))
            db.commit()

        try:
            with patch("app.workers.tasks.SessionLocal", side_effect=make_session), patch(
                "app.workers.tasks.execute_run", side_effect=make_ready_without_geometry
            ):
                result = optimize_planning_run.run(run_id)
            self.assertEqual(result["status"], "failed")
            with Session(self.engine) as db:
                run = db.get(PlanningRun, run_id)
                assignment = db.get(InvestigationAssignment, assignment_id)
                shift = db.query(AgentShift).filter_by(agent_id=agent_id, work_date=_work_date()).one()
                self.assertEqual(run.error_code, "route_geometry_incomplete")
                self.assertEqual(assignment.auto_route_status, "failed")
                self.assertIsNone(shift.current_planning_run_id)
        finally:
            self.engine.dispose()


if __name__ == "__main__":
    unittest.main()
