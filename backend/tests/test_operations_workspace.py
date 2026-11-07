import importlib.util
import unittest
from datetime import date, datetime, timezone
from io import StringIO
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch
from zoneinfo import ZoneInfo

import httpx
from fastapi import HTTPException
from alembic.migration import MigrationContext
from alembic.operations import Operations
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool
from app.database import Base
from app.database.session import get_db
from app.main import app
from app.models import AgentShift, Investigation, InvestigationAssignment, PlanningItem, PlanningRoute, PlanningRun, User
from app.models.report import InvestigationReport
from app.schemas.planning import AgentShiftInput, PlanningRouteOverviewResponse
from app.services import planning
from app.services.planning import PlanningConflict, apply_run
from app.services.geospatial import cells_for_point
from app.services.routing import OSRMClient, RoutingUnavailable
from app.utils.auth import get_current_user, require_roles
from app.utils.features import require_planning_enabled


class RoadGeometryTests(unittest.TestCase):
    def test_route_request_axis_order_and_validated_geojson(self):
        client = OSRMClient("http://osrm")
        self.addCleanup(client.close)
        response = Mock()
        response.json.return_value = {"code": "Ok", "routes": [{"geometry": {"type": "LineString", "coordinates": [[121, 14.5], [121.1, 14.6]]}, "distance": 1200, "duration": 180}]}
        client.client = SimpleNamespace(get=Mock(return_value=response), close=Mock())
        route = client.route([(14.5, 121), (14.6, 121.1)])
        request = client.client.get.call_args
        self.assertIn("121.000000,14.500000;121.100000,14.600000", request.args[0])
        self.assertEqual(request.kwargs["params"]["geometries"], "geojson")
        self.assertEqual(request.kwargs["params"]["exclude"], "ferry")
        self.assertEqual(route["distance"], 1200)
        for geometry in (None, [], {"type": "Point", "coordinates": [121, 14]}, {"type": "LineString", "coordinates": [[121, 14], [float("nan"), 14]]}, {"type": "LineString", "coordinates": [[121, 14]]}):
            response.json.return_value["routes"][0]["geometry"] = geometry
            with self.subTest(geometry=geometry), self.assertRaises(RoutingUnavailable):
                client.route([(14, 121), (15, 122)])

    def test_geometry_uses_vroom_order_and_keeps_failed_proposal(self):
        shift = SimpleNamespace(
            agent_id=7,
            work_date=date(2026, 11, 4),
            shift_starts_at=datetime(2026, 11, 4, 0, tzinfo=timezone.utc),
            shift_ends_at=datetime(2026, 11, 4, 9, tzinfo=timezone.utc),
            last_completed_at=None,
            last_completed_latitude=None,
            last_completed_longitude=None,
            start_latitude=14.1,
            start_longitude=121.1,
            end_latitude=14.9,
            end_longitude=121.9,
            start_location_label="Office",
            end_location_label="End",
        )
        cases = [SimpleNamespace(id=1, latitude=14.2, longitude=121.2), SimpleNamespace(id=2, latitude=14.3, longitude=121.3)]
        outcomes = {1: {"investigation_id": 1, "agent_id": 7, "outcome": "assigned", "sequence": 2}, 2: {"investigation_id": 2, "agent_id": 7, "outcome": "assigned", "sequence": 1}}
        osrm = Mock()
        osrm.route.return_value = {"geometry": {"type": "LineString", "coordinates": [[121.1, 14.1], [121.3, 14.3], [121.2, 14.2], [121.9, 14.9]]}, "distance": 1000, "duration": 200}
        result = planning._build_route_geometries(osrm, cases, [shift], outcomes)
        osrm.route.assert_called_once_with([(14.1, 121.1), (14.3, 121.3), (14.2, 121.2), (14.9, 121.9)])
        self.assertEqual(result[0]["geometry_status"], "ready")
        osrm.route.side_effect = RoutingUnavailable("osrm_route_unavailable")
        failed = planning._build_route_geometries(osrm, cases, [shift], outcomes)[0]
        self.assertEqual(failed["geometry_status"], "failed")
        self.assertIsNone(failed["geometry"])
        self.assertEqual(failed["geometry_error_code"], "osrm_route_unavailable")


class WorkspaceAPITests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine)
        self.supervisor = User(name="Supervisor", email="supervisor@example.test", role="supervisor", password="hash")
        self.admin = User(name="Admin", email="admin@example.test", role="admin", password="hash")
        self.agent = User(name="Agent", email="agent@example.test", role="agent", password="hash")
        self.other = User(name="Other", email="other@example.test", role="agent", password="hash")
        self.db.add_all([self.supervisor, self.admin, self.agent, self.other]); self.db.flush()
        self.case = Investigation(reference_number="INV-001", first_name="Fictional", last_name="Subject", house_number="12", street="Example Road", region_code="1300000000", priority="high", status="pending", latitude=14.5, longitude=121, location_source="manual", location_confirmed_at=datetime.now(timezone.utc), **cells_for_point(14.5, 121))
        self.second = Investigation(reference_number="INV-002", first_name="Another", last_name="Subject", house_number="15", street="Second Road", region_code="1300000000", priority="urgent", status="assigned", assigned_agent_id=self.other.id)
        self.db.add_all([self.case, self.second]); self.db.commit()
        self.actor = self.supervisor
        app.dependency_overrides[get_db] = lambda: self.db
        app.dependency_overrides[get_current_user] = lambda: self.actor
        app.dependency_overrides[require_planning_enabled] = lambda: None
        self.client = TestClient(app)

    def tearDown(self):
        app.dependency_overrides.clear(); self.client.close(); self.db.close(); self.engine.dispose()

    def test_paginated_search_facets_and_agent_boundary(self):
        payload = self.client.get("/investigations/", params={"q": "Example Road", "page_size": 1}).json()
        self.assertEqual(payload["total"], 1)
        self.assertEqual(payload["items"][0]["reference_number"], "INV-001")
        self.assertEqual(self.client.get("/investigations/", params={"q": "Fictional Subject"}).json()["total"], 1)
        self.assertEqual(payload["facets"]["location_unconfirmed"], 1)
        self.assertEqual(self.client.get("/investigations/", params={"sort": "priority", "direction": "desc"}).json()["items"][0]["priority"], "urgent")
        self.assertEqual(self.client.get("/investigations/", params={"location_confirmed": "false"}).json()["total"], 1)
        self.actor = self.agent
        self.assertEqual(self.client.get("/investigations/").json()["total"], 0)
        self.assertEqual(self.client.get(f"/investigations/{self.second.id}").status_code, 403)
        self.assertEqual(self.client.get("/planning/agent-shifts?work_date=2026-11-04").status_code, 403)
        self.assertEqual(self.client.get("/reports/review-queue").status_code, 403)

    def test_no_contact_attempt_is_visible_to_admin_and_cancellable(self):
        from app.models.route_event import InvestigationRouteEvent

        event = InvestigationRouteEvent(
            investigation_id=self.second.id,
            agent_id=self.other.id,
            work_date=datetime.now(timezone.utc).date(),
            event_type="no_contact",
            state="deferred",
            retry_number=0,
            reason="nobody_at_location",
            notes=None,
            attempted_at=datetime.now(timezone.utc),
        )
        self.db.add(event)
        self.db.commit()

        detail = self.client.get(f"/investigations/{self.second.id}").json()
        self.assertEqual(detail["active_no_contact_event"]["event_id"], event.id)
        self.assertEqual(detail["active_no_contact_event"]["state"], "deferred")

        queue = self.client.get("/investigations/awaiting-no-contact-review").json()
        self.assertEqual(queue["total"], 1)
        self.assertEqual(queue["items"][0]["investigation_id"], self.second.id)
        self.assertEqual(queue["items"][0]["event_id"], event.id)

        self.actor = self.agent
        self.assertEqual(
            self.client.get("/investigations/awaiting-no-contact-review").status_code, 403,
        )
        self.assertEqual(
            self.client.post(f"/investigations/{self.second.id}/no-contact-events/{event.id}/cancel").status_code,
            403,
        )

        self.actor = self.supervisor
        cancelled = self.client.post(f"/investigations/{self.second.id}/no-contact-events/{event.id}/cancel")
        self.assertEqual(cancelled.status_code, 200, cancelled.text)
        body = cancelled.json()
        self.assertEqual(body["status"], "cancelled")
        self.assertIsNotNone(body["reopen_on"])
        self.assertIsNone(body["active_no_contact_event"])

        repeat = self.client.post(f"/investigations/{self.second.id}/no-contact-events/{event.id}/cancel")
        self.assertEqual(repeat.status_code, 409)

        empty_queue = self.client.get("/investigations/awaiting-no-contact-review").json()
        self.assertEqual(empty_queue["total"], 0)

    def test_report_queue_latest_version_and_hidden_deleted(self):
        self.db.add_all([InvestigationReport(investigation_id=self.case.id, author_id=self.agent.id, version=1, content="Old", status="approved"), InvestigationReport(investigation_id=self.case.id, author_id=self.agent.id, version=2, content="New", status="submitted")]); self.db.commit()
        queue = self.client.get("/reports/review-queue").json()
        self.assertEqual(queue["total"], 1); self.assertEqual(queue["items"][0]["version"], 2)
        self.assertEqual(self.client.get("/reports/review-queue", params={"q": "Fictional Subject"}).json()["total"], 1)
        self.assertEqual(self.client.get("/reports/review-queue?status=approved").json()["total"], 0)
        self.case.deleted_at = datetime.now(timezone.utc); self.db.commit()
        self.assertEqual(self.client.get("/reports/review-queue").json()["total"], 0)

    def test_readiness_points_density_and_shift_metadata(self):
        work_date = datetime.now(ZoneInfo("Asia/Manila")).date()
        work_date_text = work_date.isoformat()
        response = self.client.put(
            f"/planning/agents/{self.agent.id}/shifts/{work_date_text}",
            json={
                "work_date": work_date_text,
                "region_code": "1300000000",
                "shift_starts_at": f"{work_date_text}T00:00:00+08:00",
                "shift_ends_at": f"{work_date_text}T23:59:59+08:00",
                "start_latitude": 14.55,
                "start_longitude": 121.05,
                "max_visits": 8,
                "max_open_cases": 20,
                "start_location_label": "Configured office",
                "start_location_source": "manual",
            },
        )
        self.assertEqual(response.status_code, 200, response.text)
        for resolution in (7, 8, 9):
            result = self.client.get(f"/planning/readiness?work_date={work_date_text}&region_code=1300000000&resolution={resolution}")
            self.assertEqual(result.status_code, 200, result.text)
            data = result.json(); self.assertEqual(data["available_agents"][0]["start"]["label"], "Configured office")
            self.assertEqual(data["active_agent_count"], 2)
            self.assertEqual(data["unavailable_agent_count"], 1)
            self.assertEqual(data["eligible_cases"][0]["latitude"], 14.5)
            polygon = data["density"][0]["geometry"]; self.assertEqual(polygon["type"], "Polygon"); self.assertEqual(polygon["coordinates"][0][0], polygon["coordinates"][0][-1])
        self.assertEqual(len(self.client.get(f"/planning/agent-shifts?work_date={work_date_text}").json()), 2)

    def test_route_overview_recognizes_assigned_agent_and_hides_stale_stop_sets(self):
        work_date = date(2026, 11, 4)
        shift = planning.set_agent_shift(
            self.db,
            self.agent.id,
            AgentShiftInput(
                work_date=work_date,
                region_code="1300000000",
                shift_starts_at="2026-11-04T08:00:00+08:00",
                shift_ends_at="2026-11-04T17:00:00+08:00",
                start_latitude=14.6,
                start_longitude=121.1,
                start_location_label="District Office",
                max_visits=8,
                max_open_cases=20,
            ),
        )
        self.case.assigned_agent_id = self.agent.id
        self.case.status = "assigned"
        assignment = InvestigationAssignment(
            investigation_id=self.case.id,
            agent_id=self.agent.id,
            assigned_by_id=self.supervisor.id,
            auto_route_status="published",
            auto_route_work_date=work_date,
            auto_route_agent_ids=[self.agent.id],
            auto_route_run_ids=[],
            auto_route_errors=[],
        )
        run = PlanningRun(
            requested_by_id=self.supervisor.id,
            work_date=work_date,
            region_code="1300000000",
            investigation_ids=[self.case.id],
            agent_ids=[self.agent.id],
            locked_assignments=[{"investigation_id": self.case.id, "agent_id": self.agent.id}],
            status="applied",
            auto_publish=True,
            warnings=[{
                "type": "priority_order",
                "agent_id": self.agent.id,
                "investigation_id": self.case.id,
                "reference_number": "INV-001",
                "deferred_investigation_id": 22,
                "deferred_reference_number": "INV-002",
                "reason": "schedule_constraint",
            }, {
                "type": "priority_order",
                "agent_id": self.agent.id,
                "investigation_id": None,
                "reference_number": None,
                "deferred_investigation_id": None,
                "deferred_reference_number": None,
                "reason": "search_limit",
            }],
        )
        self.db.add_all([assignment, run])
        self.db.flush()
        assignment.auto_route_run_ids = [run.id]
        self.db.add_all([
            PlanningItem(
                planning_run_id=run.id,
                investigation_id=self.case.id,
                agent_id=self.agent.id,
                outcome="assigned",
                sequence=1,
                estimated_arrival_at=datetime(2026, 11, 4, 1, 30, tzinfo=timezone.utc),
                planned_arrival_at=datetime(2026, 11, 4, 2, 0, tzinfo=timezone.utc),
                estimated_service_start_at=datetime(2026, 11, 4, 2, 5, tzinfo=timezone.utc),
                waiting_seconds=300,
                travel_seconds=300,
                travel_metres=1200,
            ),
            PlanningRoute(
                planning_run_id=run.id,
                agent_id=self.agent.id,
                geometry_status="ready",
                geometry={"type": "LineString", "coordinates": [[121.1, 14.6], [121.0, 14.5]]},
                geometry_digest=planning._digest({"type": "LineString", "coordinates": [[121.1, 14.6], [121.0, 14.5]]}),
                total_distance_metres=1200,
                total_travel_seconds=300,
                planned_departure_at=datetime(2026, 11, 4, 1, 45, tzinfo=timezone.utc),
                start={"latitude": 14.6, "longitude": 121.1, "label": "District Office"},
            ),
        ])
        shift.current_planning_run_id = run.id
        self.db.commit()

        data = PlanningRouteOverviewResponse.model_validate(
            planning.planning_route_overview(self.db, work_date, "1300000000")
        ).model_dump(mode="json")
        route_agent = next(item for item in data["agents"] if item["id"] == self.agent.id)
        self.assertEqual(route_agent["route_status"], "published")
        self.assertEqual(route_agent["priority_order_warnings"], [{
            "investigation_id": self.case.id,
            "reference_number": "INV-001",
            "deferred_investigation_id": 22,
            "deferred_reference_number": "INV-002",
            "reason": "schedule_constraint",
        }, {
            "investigation_id": None,
            "reference_number": None,
            "deferred_investigation_id": None,
            "deferred_reference_number": None,
            "reason": "search_limit",
        }])
        self.assertEqual(route_agent["stops"][0]["investigation_id"], self.case.id)
        self.assertEqual(route_agent["route"]["agent_name"], self.agent.name)
        self.assertEqual(
            route_agent["route"]["geometry"]["coordinates"],
            [[121.1, 14.6], [121.0, 14.5]],
        )
        self.assertEqual(route_agent["shift"]["start_location_label"], "District Office")
        stop = route_agent["stops"][0]
        self.assertEqual(stop["earliest_arrival_estimate_at"], "2026-11-04T01:30:00")
        self.assertEqual(stop["planned_arrival_at"], "2026-11-04T02:00:00")
        self.assertEqual(stop["planned_waiting_seconds"], 300)
        self.assertEqual(stop["estimated_service_start_at"], "2026-11-04T02:05:00")
        self.assertEqual(route_agent["route"]["planned_departure_at"], "2026-11-04T01:45:00")
        self.assertEqual(route_agent["route"]["total_waiting_seconds"], 300)
        self.assertEqual(route_agent["route"]["total_planned_waiting_seconds"], 300)

        historical_item = self.db.query(PlanningItem).filter_by(
            planning_run_id=run.id,
            investigation_id=self.case.id,
        ).one()
        historical_route = self.db.query(PlanningRoute).filter_by(
            planning_run_id=run.id,
            agent_id=self.agent.id,
        ).one()
        historical_item.planned_arrival_at = None
        historical_item.waiting_seconds = 5400
        historical_route.planned_departure_at = None
        self.db.commit()
        historical_data = planning.planning_route_overview(
            self.db, work_date, "1300000000",
        )
        historical_agent = next(
            item for item in historical_data["agents"] if item["id"] == self.agent.id
        )
        self.assertIsNone(historical_agent["stops"][0]["planned_arrival_at"])
        self.assertIsNone(historical_agent["stops"][0]["planned_waiting_seconds"])
        self.assertIsNone(historical_agent["route"]["planned_departure_at"])
        self.assertIsNone(historical_agent["route"]["total_waiting_seconds"])
        self.assertIsNone(historical_agent["route"]["total_planned_waiting_seconds"])
        self.assertEqual(
            historical_agent["route"]["geometry"]["coordinates"],
            [[121.1, 14.6], [121.0, 14.5]],
        )

        run.region_code = "0400000000"
        self.db.commit()
        wrong_region = planning.planning_route_overview(self.db, work_date, "1300000000")
        wrong_region_agent = next(item for item in wrong_region["agents"] if item["id"] == self.agent.id)
        self.assertIsNone(wrong_region_agent["route"])
        self.assertEqual(wrong_region_agent["route_status"], "needs_refresh")
        run.region_code = "1300000000"
        self.db.commit()

        self.case.status = "completed"
        self.db.commit()
        removed_stop = planning.planning_route_overview(self.db, work_date, "1300000000")
        removed_stop_agent = next(item for item in removed_stop["agents"] if item["id"] == self.agent.id)
        self.assertIsNone(removed_stop_agent["route"])
        self.assertEqual(removed_stop_agent["stops"], [])
        self.case.status = "assigned"
        self.db.commit()

        extra_case = Investigation(
            reference_number="INV-003",
            first_name="New",
            last_name="Assignment",
            house_number="20",
            street="New Road",
            region_code="1300000000",
            priority="normal",
            status="assigned",
            assigned_agent_id=self.agent.id,
            latitude=14.55,
            longitude=121.05,
            location_source="manual",
            location_confirmed_at=datetime.now(timezone.utc),
            **cells_for_point(14.55, 121.05),
        )
        self.db.add(extra_case)
        self.db.commit()
        stale = PlanningRouteOverviewResponse.model_validate(
            planning.planning_route_overview(self.db, work_date, "1300000000")
        ).model_dump(mode="json")
        stale_agent = next(item for item in stale["agents"] if item["id"] == self.agent.id)
        self.assertIsNone(stale_agent["route"])
        self.assertEqual(stale_agent["route_status"], "needs_refresh")

    def test_route_overview_supports_all_and_region_scopes_for_admins_and_supervisors(self):
        work_date = date(2026, 11, 4)
        for agent, region_code, latitude, longitude in (
            (self.agent, "1300000000", 14.6, 121.1),
            (self.other, "0400000000", 14.3, 121.0),
        ):
            planning.set_agent_shift(
                self.db,
                agent.id,
                AgentShiftInput(
                    work_date=work_date,
                    region_code=region_code,
                    shift_starts_at="2026-11-04T08:00:00+08:00",
                    shift_ends_at="2026-11-04T17:00:00+08:00",
                    start_latitude=latitude,
                    start_longitude=longitude,
                    max_visits=8,
                    max_open_cases=20,
                ),
            )

        all_regions = PlanningRouteOverviewResponse.model_validate(
            planning.planning_route_overview(self.db, work_date)
        ).model_dump(mode="json")
        self.assertIsNone(all_regions["region_code"])
        self.assertEqual(
            {agent["region_code"] for agent in all_regions["agents"]},
            {"1300000000", "0400000000"},
        )

        selected_region = PlanningRouteOverviewResponse.model_validate(
            planning.planning_route_overview(self.db, work_date, "0400000000")
        ).model_dump(mode="json")
        self.assertEqual(selected_region["region_code"], "0400000000")
        self.assertEqual(
            {agent["id"] for agent in selected_region["agents"]},
            {self.other.id},
        )

        with self.assertRaises(PlanningConflict):
            planning.planning_route_overview(self.db, work_date, "9999999999")

        guard = require_roles("admin", "supervisor")
        self.assertIs(guard(self.supervisor), self.supervisor)
        self.assertIs(guard(self.admin), self.admin)
        with self.assertRaises(HTTPException) as denied:
            guard(self.agent)
        self.assertEqual(denied.exception.status_code, 403)

    def test_partial_geometry_blocks_automatic_publication_without_losing_items(self):
        from app.schemas.planning import AgentShiftInput, PlanningRunCreate
        shift = planning.set_agent_shift(self.db, self.agent.id, AgentShiftInput(work_date=date(2026, 11, 4), region_code="1300000000", shift_starts_at="2026-11-04T08:00:00+08:00", shift_ends_at="2026-11-04T17:00:00+08:00", start_latitude=14.6, start_longitude=121.1, max_visits=8, max_open_cases=20))
        run = planning.create_run(self.db, PlanningRunCreate(work_date=date(2026,11,4), region_code="1300000000", investigation_ids=[self.case.id], agent_ids=[self.agent.id]), self.supervisor)
        run.status="running"; run.auto_publish=True; self.db.commit()
        outcome = {self.case.id: {"investigation_id": self.case.id,"agent_id":self.agent.id,"outcome":"assigned","sequence":1}}
        osrm=Mock(); osrm.route.side_effect=RoutingUnavailable("osrm_route_unavailable")
        geometries=planning._build_route_geometries(osrm,[self.case],[shift],outcome)
        planning._record_ready_run(self.db,run,run.input_digest,[self.case],[shift],[self.agent],{}, {self.case.id:("assigned",None)},outcome,geometries)
        payload = planning.run_response(self.db, run)
        self.assertEqual(payload["status"],"ready"); self.assertFalse(payload["geometry_complete"]); self.assertEqual(len(payload["items"]),1)
        post_paths = {
            route.path
            for route in app.routes
            if "POST" in getattr(route, "methods", set())
        }
        self.assertNotIn("/planning/runs", post_paths)
        self.assertNotIn("/planning/runs/{run_id}/apply", post_paths)
        with self.assertRaisesRegex(PlanningConflict, "route_geometry_incomplete"):
            apply_run(self.db, run.id, run.result_digest, self.supervisor)
        self.assertIsNone(self.case.assigned_agent_id)
        route = self.db.query(PlanningRoute).filter_by(planning_run_id=run.id).one()
        for geometry in ({"type": "LineString", "coordinates": []}, {"type": "LineString", "coordinates": [[121, 14], [999, 14]]}, {"type": "Point", "coordinates": [121, 14]}):
            with self.subTest(geometry=geometry):
                route.geometry_status = "ready"
                route.geometry_error_code = None
                route.geometry = geometry
                route.geometry_digest = planning._digest(geometry)
                self.db.commit()
                review = planning.run_response(self.db, run)
                self.assertFalse(review["geometry_complete"])
                self.assertIsNone(review["routes"][0]["geometry"])
                with self.assertRaisesRegex(PlanningConflict, "route_geometry_incomplete"):
                    apply_run(self.db, run.id, run.result_digest, self.supervisor)

    def test_geocoder_reuses_bounded_philippine_search(self):
        from app.services import geocoding

        get = Mock()
        get.return_value.json.return_value=[{"lat":"14.5","lon":"121","display_name":"Test","osm_type":"way","osm_id":123}]
        with patch.object(geocoding, "httpx", SimpleNamespace(get=get, HTTPError=httpx.HTTPError)):
            response=geocoding.search_locations("Example")
            self.assertEqual(len(response),1)
            self.assertEqual(get.call_args.kwargs["params"]["countrycodes"],"ph"); self.assertEqual(get.call_args.kwargs["params"]["limit"],5)


class GeometryMigrationTests(unittest.TestCase):
    def test_upgrade_and_downgrade_preserve_existing_shift(self):
        spec=importlib.util.spec_from_file_location("geometry_migration",Path(__file__).parents[1]/"alembic/versions/0008_planning_route_geometry.py")
        module=importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
        engine=create_engine("sqlite:///:memory:")
        with engine.begin() as connection:
            connection.exec_driver_sql("CREATE TABLE users (id INTEGER PRIMARY KEY)")
            connection.exec_driver_sql("CREATE TABLE planning_runs (id INTEGER PRIMARY KEY)")
            connection.exec_driver_sql("CREATE TABLE agent_shifts (id INTEGER PRIMARY KEY, agent_id INTEGER)")
            connection.exec_driver_sql("INSERT INTO agent_shifts VALUES (1, 2)")
            with Operations.context(MigrationContext.configure(connection)):
                module.upgrade()
            self.assertIn("planning_routes",inspect(connection).get_table_names())
            self.assertIsNone(connection.exec_driver_sql("SELECT start_location_label FROM agent_shifts").scalar())
            with Operations.context(MigrationContext.configure(connection)):
                module.downgrade()
            self.assertEqual(connection.exec_driver_sql("SELECT agent_id FROM agent_shifts").scalar(),2)
        engine.dispose()
