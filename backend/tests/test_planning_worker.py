import unittest
from datetime import date
from unittest.mock import patch

from celery.exceptions import Retry
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.database import Base
from app.models.planning import PlanningRun
from app.models.user import User
from app.workers.tasks import optimize_planning_run


class PlanningWorkerRetryTests(unittest.TestCase):
    def test_disabled_feature_flag_fails_queued_run_without_calling_router(self):
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(engine)
        with Session(engine) as db:
            supervisor = User(name="Supervisor", email="worker-disabled@example.test", password="hash", role="supervisor")
            db.add(supervisor)
            db.flush()
            run = PlanningRun(
                requested_by_id=supervisor.id,
                work_date=date(2026, 11, 4),
                region_code="1300000000",
                investigation_ids=[1],
                agent_ids=[2],
                locked_assignments=[],
                status="queued",
            )
            db.add(run)
            db.commit()
            run_id = run.id

        def make_session():
            return Session(engine)

        try:
            with patch("app.workers.tasks.PLANNING_ENABLED", False), \
                    patch("app.workers.tasks.SessionLocal", side_effect=make_session), \
                    patch("app.workers.tasks.execute_run") as execute:
                result = optimize_planning_run.run(run_id)
            self.assertEqual(result, {"run_id": run_id, "status": "failed"})
            execute.assert_not_called()
            with Session(engine) as db:
                disabled = db.get(PlanningRun, run_id)
                self.assertEqual(disabled.error_code, "planning_disabled")
        finally:
            engine.dispose()

    def test_transient_routing_failure_requeues_run_for_bounded_celery_retry(self):
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(engine)
        with Session(engine) as db:
            supervisor = User(name="Supervisor", email="worker-retry@example.test", password="hash", role="supervisor")
            db.add(supervisor)
            db.flush()
            run = PlanningRun(
                requested_by_id=supervisor.id,
                work_date=date(2026, 11, 4),
                region_code="1300000000",
                investigation_ids=[1],
                agent_ids=[2],
                locked_assignments=[],
                status="failed",
                error_code="osrm_snap_failed",
            )
            db.add(run)
            db.commit()
            run_id = run.id

        def make_session():
            return Session(engine)

        try:
            with patch("app.workers.tasks.SessionLocal", side_effect=make_session), patch("app.workers.tasks.execute_run"):
                with patch.object(optimize_planning_run, "retry", return_value=Retry("simulated retry")) as retry:
                    with self.assertRaises(Retry):
                        optimize_planning_run.run(run_id)
                    retry.assert_called_once()
            with Session(engine) as db:
                retried = db.get(PlanningRun, run_id)
                self.assertEqual(retried.status, "queued")
                self.assertIsNone(retried.error_code)
        finally:
            engine.dispose()

    def test_overflow_followup_marker_survives_queue_failure_for_redelivery(self):
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(engine)
        with Session(engine) as db:
            supervisor = User(name="Supervisor", email="worker-overflow@example.test", password="hash", role="supervisor")
            db.add(supervisor)
            db.flush()
            run = PlanningRun(
                requested_by_id=supervisor.id,
                work_date=date(2026, 11, 4),
                region_code="1300000000",
                investigation_ids=[1],
                agent_ids=[2],
                locked_assignments=[],
                status="applied",
                auto_publish=True,
                auto_replan_requested=True,
            )
            db.add(run)
            db.commit()
            run_id = run.id

        def make_session():
            return Session(engine)

        try:
            with patch("app.workers.tasks.PLANNING_ENABLED", True), \
                    patch("app.workers.tasks.SessionLocal", side_effect=make_session), \
                    patch("app.workers.tasks.execute_run"), \
                    patch("app.workers.tasks.queue_automatic_planning", side_effect=RuntimeError("broker unavailable")):
                with self.assertRaisesRegex(RuntimeError, "broker unavailable"):
                    optimize_planning_run.run(run_id)
            with Session(engine) as db:
                persisted = db.get(PlanningRun, run_id)
                self.assertEqual(persisted.status, "applied")
                self.assertTrue(persisted.auto_replan_requested)
        finally:
            engine.dispose()


if __name__ == "__main__":
    unittest.main()
