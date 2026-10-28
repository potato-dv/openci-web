import os
import unittest
from datetime import date, datetime, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.database import Base
from app.models.investigation import Investigation
from app.models.planning import AgentShift, PlanningItem, PlanningRoute
from app.models.user import User
from app.schemas.planning import PlanningRunCreate
from app.services.geospatial import cells_for_point
from app.services.planning import create_run, execute_run, run_response
from app.services.routing import valid_route_geometry


@unittest.skipUnless(
    os.getenv("OPENCI_TEST_LIVE_ROUTING") == "1",
    "Set OPENCI_TEST_LIVE_ROUTING=1 with OSRM and VROOM available",
)
class LiveRoutingIntegrationTests(unittest.TestCase):
    def test_non_production_fixture_reaches_ready_with_real_road_geometry(self):
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(engine)
        work_date = date(2026, 11, 4)

        try:
            with Session(engine) as db:
                supervisor = User(
                    name="Integration Planner",
                    email="integration-planner@example.test",
                    password="not-a-real-password",
                    role="supervisor",
                )
                agent = User(
                    name="Integration Agent",
                    email="integration-agent@example.test",
                    password="not-a-real-password",
                    role="agent",
                )
                db.add_all([supervisor, agent])
                db.flush()

                case_latitude, case_longitude = 14.5896, 120.9819
                cells = cells_for_point(case_latitude, case_longitude)
                investigation = Investigation(
                    reference_number="INV-LIVE-ROUTING-001",
                    first_name="Routing",
                    last_name="Fixture",
                    region_code="1300000000",
                    latitude=case_latitude,
                    longitude=case_longitude,
                    location_source="manual",
                    location_confirmed_at=datetime(2026, 11, 1, tzinfo=timezone.utc),
                    location_confirmed_by_id=supervisor.id,
                    h3_r7=cells["h3_r7"],
                    h3_r8=cells["h3_r8"],
                    h3_r9=cells["h3_r9"],
                    status="pending",
                    priority="normal",
                )
                shift = AgentShift(
                    agent_id=agent.id,
                    work_date=work_date,
                    region_code="1300000000",
                    is_available=True,
                    shift_starts_at=datetime(2026, 11, 4, 0, tzinfo=timezone.utc),
                    shift_ends_at=datetime(2026, 11, 4, 9, tzinfo=timezone.utc),
                    start_latitude=14.5995,
                    start_longitude=120.9842,
                    max_visits=4,
                    max_open_cases=10,
                )
                db.add_all([investigation, shift])
                db.flush()

                run = create_run(
                    db,
                    PlanningRunCreate(
                        work_date=work_date,
                        region_code="1300000000",
                        investigation_ids=[investigation.id],
                        agent_ids=[agent.id],
                    ),
                    supervisor,
                )

                execute_run(db, run.id)
                db.refresh(run)

                item = db.query(PlanningItem).filter_by(planning_run_id=run.id).one()
                route = db.query(PlanningRoute).filter_by(planning_run_id=run.id).one()
                response = run_response(db, run)

                self.assertEqual(run.status, "ready", run.error_code)
                self.assertEqual(item.outcome, "assigned")
                self.assertEqual(route.geometry_status, "ready")
                self.assertTrue(valid_route_geometry(route.geometry))
                self.assertGreater(route.total_distance_metres, 0)
                self.assertTrue(response["geometry_complete"])
                self.assertNotIn("approval_blocked_reason", response)
                self.assertIsNone(run.applied_at)
        finally:
            engine.dispose()


if __name__ == "__main__":
    unittest.main()
