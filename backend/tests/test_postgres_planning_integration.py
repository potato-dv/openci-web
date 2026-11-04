"""PostgreSQL integration coverage for locking and plan publication.

Set OPENCI_TEST_POSTGRES_URL to an empty, disposable PostgreSQL database to run
this test. The test creates and drops a private schema inside that database.
"""

import os
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timezone
from threading import Barrier
from uuid import uuid4
from unittest.mock import patch

from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import Base
from app.models import AgentShift, Investigation, InvestigationAssignment, PlanningRun, User
from app.schemas.planning import PlanningRunCreate
from app.services.geospatial import cells_for_point
from app.services import planning as planning_service
from app.services.planning import PlanningConflict, apply_run, execute_run


POSTGRES_URL = os.getenv("OPENCI_TEST_POSTGRES_URL")


@unittest.skipUnless(POSTGRES_URL, "set OPENCI_TEST_POSTGRES_URL to run PostgreSQL integration tests")
class PostgreSQLPlanningIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.schema = f"openci_test_{uuid4().hex}"
        cls.admin_engine = create_engine(POSTGRES_URL)
        with cls.admin_engine.begin() as connection:
            connection.execute(text(f'CREATE SCHEMA "{cls.schema}"'))
        cls.engine = create_engine(
            POSTGRES_URL,
            connect_args={"options": f"-csearch_path={cls.schema}"},
        )
        Base.metadata.create_all(cls.engine)

    @classmethod
    def tearDownClass(cls):
        if hasattr(cls, "engine"):
            cls.engine.dispose()
        if hasattr(cls, "admin_engine"):
            with cls.admin_engine.begin() as connection:
                connection.execute(text(f'DROP SCHEMA IF EXISTS "{cls.schema}" CASCADE'))
            cls.admin_engine.dispose()

    def test_postgres_concurrent_automatic_publication_is_idempotent_and_preserves_active_assignment_invariant(self):
        work_date = date(2026, 11, 4)

        class Router:
            def __init__(self):
                pass

            @staticmethod
            def nearest_many(coordinates):
                return [{"distance": 25} for _ in coordinates]

            @staticmethod
            def route(coordinates):
                return {"geometry": {"type": "LineString", "coordinates": [[lon, lat] for lat, lon in coordinates]}, "distance": 5000, "duration": 600}

            @staticmethod
            def table(coordinates):
                count = len(coordinates)
                return {
                    "durations": [[0 if i == j else 600 for j in range(count)] for i in range(count)],
                    "distances": [[0 if i == j else 5000 for j in range(count)] for i in range(count)],
                }

            @staticmethod
            def close():
                pass

        class Solver:
            def __init__(self):
                pass

            @staticmethod
            def solve(_payload):
                return {
                    "routes": [{
                        "vehicle": agent_id,
                        "steps": [
                            {"type": "start", "arrival": int(datetime(2026, 11, 4, 0, tzinfo=timezone.utc).timestamp()), "waiting_time": 0},
                            {"type": "job", "id": investigation_id, "arrival": int(datetime(2026, 11, 4, 0, 10, tzinfo=timezone.utc).timestamp()), "waiting_time": 0},
                            {"type": "end", "arrival": int(datetime(2026, 11, 4, 1, 5, tzinfo=timezone.utc).timestamp())},
                        ],
                    }],
                    "unassigned": [],
                }

            @staticmethod
            def close():
                pass

        with Session(self.engine) as db:
            supervisor = User(
                name="Test Supervisor",
                email=f"supervisor-{uuid4().hex}@example.test",
                password="test-only",
                role="supervisor",
            )
            agent = User(
                name="Test Agent",
                email=f"agent-{uuid4().hex}@example.test",
                password="test-only",
                role="agent",
            )
            db.add_all([supervisor, agent])
            db.flush()

            cells = cells_for_point(14.6507, 121.0494)
            case = Investigation(
                reference_number=f"INV-TEST-{uuid4().hex[:20]}",
                first_name="Fictional",
                last_name="Case",
                house_number="10",
                street="Test Road",
                region_code="1300000000",
                status="pending",
                priority="high",
                latitude=14.6507,
                longitude=121.0494,
                location_source="manual",
                location_confirmed_at=datetime(2026, 11, 1, tzinfo=timezone.utc),
                location_confirmed_by_id=supervisor.id,
                h3_r7=cells["h3_r7"],
                h3_r8=cells["h3_r8"],
                h3_r9=cells["h3_r9"],
            )
            db.add(case)
            db.flush()
            shift = AgentShift(
                agent_id=agent.id,
                work_date=work_date,
                region_code="1300000000",
                is_available=True,
                shift_starts_at=datetime(2026, 11, 4, 0, tzinfo=timezone.utc),
                shift_ends_at=datetime(2026, 11, 4, 9, tzinfo=timezone.utc),
                start_latitude=14.6,
                start_longitude=121.1,
                max_visits=4,
                max_open_cases=10,
            )
            db.add(shift)
            db.flush()
            investigation_id = case.id
            agent_id = agent.id

            run = planning_service.create_run(
                db,
                PlanningRunCreate(
                    work_date=work_date,
                    region_code="1300000000",
                    investigation_ids=[case.id],
                    agent_ids=[agent.id],
                ),
                supervisor,
            )
            competing_run = planning_service.create_run(
                db,
                PlanningRunCreate(
                    work_date=work_date,
                    region_code="1300000000",
                    investigation_ids=[case.id],
                    agent_ids=[agent.id],
                ),
                supervisor,
            )
            run.auto_publish = True
            competing_run.auto_publish = True
            db.commit()
            for queued_run in (run, competing_run):
                with patch.object(planning_service, "OSRMClient", Router), patch.object(planning_service, "VROOMClient", Solver):
                    execute_run(db, queued_run.id)

            db.refresh(run)
            db.refresh(competing_run)
            self.assertEqual(run.status, "ready")
            self.assertEqual(competing_run.status, "ready")

            publication_barrier = Barrier(2)

            def publish_concurrently(run_id):
                with Session(self.engine) as approval_db:
                    plan = approval_db.get(PlanningRun, run_id)
                    actor = approval_db.get(User, supervisor.id)
                    publication_barrier.wait(timeout=10)
                    try:
                        result = apply_run(approval_db, run_id, plan.result_digest, actor)
                        return result.status
                    except PlanningConflict as error:
                        return str(error)

            with ThreadPoolExecutor(max_workers=2) as pool:
                publication_results = list(pool.map(publish_concurrently, (run.id, competing_run.id)))
            self.assertCountEqual(publication_results, ["applied", "stale_plan"])

            db.expire_all()
            applied_run = next(
                db.get(PlanningRun, run_id)
                for run_id in (run.id, competing_run.id)
                if db.get(PlanningRun, run_id).status == "applied"
            )
            stale_run = next(
                db.get(PlanningRun, run_id)
                for run_id in (run.id, competing_run.id)
                if db.get(PlanningRun, run_id).status == "stale"
            )
            self.assertEqual(stale_run.error_code, "inputs_changed")
            self.assertEqual(apply_run(db, applied_run.id, applied_run.result_digest, supervisor).status, "applied")
            self.assertEqual(db.get(Investigation, investigation_id).assigned_agent_id, agent_id)
            self.assertEqual(db.get(AgentShift, shift.id).current_planning_run_id, applied_run.id)
            self.assertEqual(
                db.query(InvestigationAssignment).filter_by(
                    investigation_id=investigation_id,
                    is_active=True,
                ).count(),
                1,
            )

            repeated = apply_run(db, applied_run.id, applied_run.result_digest, supervisor)
            self.assertEqual(repeated.status, "applied")
            self.assertEqual(
                db.query(InvestigationAssignment).filter_by(
                    investigation_id=investigation_id,
                    is_active=True,
                ).count(),
                1,
            )

            db.add(InvestigationAssignment(
                investigation_id=investigation_id,
                agent_id=agent_id,
                assigned_by_id=supervisor.id,
                is_active=True,
            ))
            with self.assertRaises(IntegrityError):
                db.commit()
            db.rollback()
            self.assertEqual(
                db.query(InvestigationAssignment).filter_by(
                    investigation_id=investigation_id,
                    is_active=True,
                ).count(),
                1,
            )


if __name__ == "__main__":
    unittest.main()
