import unittest
from datetime import date, datetime, timezone

from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.database import Base
from app.models.investigation import Investigation
from app.models.planning import PlanningRun
from app.models.user import User
from app.schemas.planning import AgentShiftInput
from app.routes.planning import get_agent_shift, get_readiness, published_agent_route, put_agent_shift
from app.services.geospatial import cells_for_point
from app.utils.auth import require_roles


class PlanningRouteTests(unittest.TestCase):
    def test_supervisor_can_create_and_read_shift_but_agent_cannot_read_planning_data(self):
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(engine)
        work_date = date(2026, 11, 4)
        with Session(engine) as db:
            supervisor = User(name="Supervisor", email="supervisor-route@example.test", password="hash", role="supervisor")
            agent = User(name="Agent", email="agent-route@example.test", password="hash", role="agent")
            db.add_all([supervisor, agent])
            db.commit()
            agent_id = agent.id

            self.assertIsNone(get_agent_shift(agent_id, work_date, db, supervisor))
            values = AgentShiftInput(
                work_date=work_date,
                region_code="1300000000",
                is_available=True,
                shift_starts_at="2026-11-04T08:00:00+08:00",
                shift_ends_at="2026-11-04T17:00:00+08:00",
                start_latitude=14.6,
                start_longitude=121.1,
                max_visits=8,
                max_open_cases=20,
            )
            saved = put_agent_shift(agent_id, work_date, values, db, supervisor)
            self.assertEqual(saved.max_visits, 8)
            self.assertEqual(get_agent_shift(agent_id, work_date, db, supervisor).region_code, "1300000000")
            cells = cells_for_point(14.6, 121.1)
            case = Investigation(
                reference_number="INV-ASSIGNED-ROUTE-001",
                first_name="Assigned",
                last_name="Case",
                house_number="10",
                street="Example Street",
                region_code="1300000000",
                status="assigned",
                priority="normal",
                latitude=14.6,
                longitude=121.1,
                location_source="manual",
                location_confirmed_at=datetime(2026, 11, 4, tzinfo=timezone.utc),
                location_confirmed_by_id=supervisor.id,
                h3_r7=cells["h3_r7"],
                h3_r8=cells["h3_r8"],
                h3_r9=cells["h3_r9"],
                assigned_agent_id=agent_id,
            )
            db.add(case)
            unlocated_case = Investigation(
                reference_number="INV-ASSIGNED-ROUTE-002",
                first_name="Unlocated",
                last_name="Case",
                house_number="20",
                street="Example Street",
                region_code="1300000000",
                status="assigned",
                priority="normal",
                assigned_agent_id=agent_id,
            )
            db.add(unlocated_case)
            db.commit()

            run = PlanningRun(
                requested_by_id=supervisor.id,
                work_date=work_date,
                region_code="1300000000",
                investigation_ids=[case.id],
                agent_ids=[agent_id],
                locked_assignments=[],
                status="queued",
                auto_publish=True,
            )
            db.add(run)
            db.commit()
            pending_route = published_agent_route(db, agent, work_date)
            self.assertEqual(pending_route["reason"], "route_refresh_pending")
            self.assertEqual(pending_route["stops"], [])

            run.status = "failed"
            db.commit()
            failed_route = published_agent_route(db, agent, work_date)
            self.assertEqual(failed_route["reason"], "route_needs_refresh")

            readiness = get_readiness(work_date, "1300000000", 8, db, supervisor)
            self.assertEqual(readiness["available_agents"][0]["id"], agent_id)
            self.assertEqual(readiness["eligible_cases"][0]["assigned_agent_id"], agent_id)
            self.assertEqual(readiness["eligible_cases"][0]["assigned_agent_name"], "Agent")
            self.assertEqual(readiness["excluded_cases"][0]["assigned_agent_id"], agent_id)
            self.assertEqual(readiness["excluded_cases"][0]["assigned_agent_name"], "Agent")

            with self.assertRaises(HTTPException) as denied:
                require_roles("admin", "supervisor")(agent)
            self.assertEqual(denied.exception.status_code, 403)
        engine.dispose()


if __name__ == "__main__":
    unittest.main()
