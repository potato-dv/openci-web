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
from app.schemas.planning import LocationConfirm, LockedAssignment, PlanningRunCreate
from app.services.geospatial import cells_for_point
from app.services.investigation import assign_investigation
from app.services.planning import create_run, planning_route_overview, queue_shift_route_refresh
from app.controllers.investigation import assign
from app.routes.investigation import confirm_investigation_location, retry_investigation_route_refresh
from app.workers.tasks import optimize_planning_run


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
            with patch("app.workers.tasks.SessionLocal", side_effect=make_session), patch(
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
