import json
import unittest
from datetime import date, datetime, time, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import Mock, patch
from zoneinfo import ZoneInfo

import h3
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.database import Base
from app.models.investigation import Investigation
from app.models.planning import AgentShift, PlanningItem, PlanningRun
from app.models.user import User
from app.schemas.investigation import InvestigationUpdate
from app.schemas.planning import AgentShiftInput, PlanningRunCreate
from app.services.geospatial import cells_for_point, neighboring_cells, validate_coordinates
from app.services.geocoding import suggest_locations
from app.services.locations import catalog
from app.services.investigation import update_investigation
from app.services.planning import (
    _connected_components,
    _log_planning_event,
    _record_ready_run,
    _region_skill,
    _route_origin,
    _run_component,
    PlanningConflict,
    apply_run,
    execute_run,
)
from app.services.routing import OSRMClient, RoutingUnavailable, VROOMClient


class GeospatialIndexTests(unittest.TestCase):
    def test_confirmed_point_has_direct_h3_indexes_at_requested_resolutions(self):
        # Fictional field office point in Quezon City.
        cells = cells_for_point(14.6507, 121.0494)
        self.assertEqual(set(cells), {"h3_r7", "h3_r8", "h3_r9"})
        self.assertEqual(h3.get_resolution(cells["h3_r7"]), 7)
        self.assertEqual(h3.get_resolution(cells["h3_r8"]), 8)
        self.assertEqual(h3.get_resolution(cells["h3_r9"]), 9)

    def test_neighbor_lookup_includes_center_and_adjacent_cells(self):
        cell = cells_for_point(14.6507, 121.0494)["h3_r8"]
        neighbors = neighboring_cells(cell, 1)
        self.assertIn(cell, neighbors)
        self.assertEqual(len(neighbors), 7)

    def test_coordinate_validation_rejects_out_of_range_values(self):
        self.assertIsNone(validate_coordinates(14.5, 121.0))
        with self.assertRaises(ValueError):
            validate_coordinates(121.0, 14.5)

    def test_coordinates_without_supervisor_confirmation_are_not_confirmed(self):
        case = Investigation(latitude=14.5, longitude=121.0, location_source="manual")
        self.assertFalse(case.location_confirmed)

    def test_address_edit_invalidates_confirmed_location_and_plans(self):
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(engine)
        with Session(engine) as db:
            supervisor = User(name="Planner", email="planner-location@example.test", password="hash", role="supervisor")
            agent = User(name="Field Agent", email="agent-location@example.test", password="hash", role="agent")
            db.add_all([supervisor, agent])
            db.flush()

            cells = cells_for_point(14.6507, 121.0494)
            case = Investigation(
                reference_number="INV-PLAN-LOCATION-001",
                first_name="Fictional",
                last_name="Case",
                house_number="10",
                street="Old Test Street",
                region_code="1300000000",
                status="assigned",
                priority="normal",
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

            applied = PlanningRun(
                requested_by_id=supervisor.id,
                work_date=datetime(2026, 11, 4, tzinfo=timezone.utc).date(),
                region_code="1300000000",
                investigation_ids=[case.id],
                agent_ids=[agent.id],
                status="applied",
            )
            ready = PlanningRun(
                requested_by_id=supervisor.id,
                work_date=datetime(2026, 11, 4, tzinfo=timezone.utc).date(),
                region_code="1300000000",
                investigation_ids=[case.id],
                agent_ids=[agent.id],
                status="ready",
            )
            db.add_all([applied, ready])
            db.flush()
            shift = AgentShift(
                agent_id=agent.id,
                work_date=applied.work_date,
                region_code="1300000000",
                shift_starts_at=datetime(2026, 11, 4, 0, tzinfo=timezone.utc),
                shift_ends_at=datetime(2026, 11, 4, 9, tzinfo=timezone.utc),
                start_latitude=14.6,
                start_longitude=121.1,
                max_visits=4,
                max_open_cases=10,
                current_planning_run_id=applied.id,
            )
            db.add_all([
                shift,
                PlanningItem(planning_run_id=applied.id, investigation_id=case.id, agent_id=agent.id, outcome="assigned", sequence=1),
                PlanningItem(planning_run_id=ready.id, investigation_id=case.id, agent_id=agent.id, outcome="assigned", sequence=1),
            ])
            db.commit()

            update_investigation(db, case, InvestigationUpdate(street="New Test Street"))

            db.refresh(case)
            db.refresh(ready)
            db.refresh(shift)
            self.assertIsNone(case.latitude)
            self.assertIsNone(case.longitude)
            self.assertIsNone(case.location_source)
            self.assertIsNone(case.location_confirmed_at)
            self.assertIsNone(case.location_confirmed_by_id)
            self.assertEqual((case.h3_r7, case.h3_r8, case.h3_r9), (None, None, None))
            self.assertEqual(ready.status, "stale")
            self.assertEqual(ready.error_code, "investigation_changed")
            self.assertEqual(db.get(PlanningRun, applied.id).status, "applied")
            self.assertIsNone(shift.current_planning_run_id)
        engine.dispose()


class PlanningObservabilityTests(unittest.TestCase):
    def test_lifecycle_event_is_emitted_as_json_without_case_location_fields(self):
        with self.assertLogs("app.planning", level="INFO") as captured:
            _log_planning_event(
                "planning.run_ready",
                planning_run_id=42,
                assigned_count=2,
                unassigned_reasons={"no_road_connected_agent": 1},
            )

        event_text = captured.output[0].split("planning_event ", 1)[1]
        payload = json.loads(event_text)
        self.assertEqual(payload["event"], "planning.run_ready")
        self.assertEqual(payload["assigned_count"], 2)
        self.assertNotIn("latitude", payload)
        self.assertNotIn("longitude", payload)
        self.assertNotIn("address", payload)


class PlanningInputTests(unittest.TestCase):
    def test_optimizer_and_schedule_validator_share_the_same_clock_snapshot(self):
        work_date = datetime.now(ZoneInfo("Asia/Manila")).date()
        planned_at = datetime.combine(work_date, time(10), tzinfo=ZoneInfo("Asia/Manila"))
        later_now = planned_at + timedelta(minutes=1)
        case = SimpleNamespace(
            id=401,
            latitude=14.5,
            longitude=121.0,
            service_duration_seconds=300,
            priority="normal",
            region_code="1300000000",
            visit_not_before_at=None,
            visit_due_at=None,
            assigned_agent_id=None,
        )
        shift = SimpleNamespace(
            agent_id=7,
            work_date=work_date,
            region_code="1300000000",
            start_latitude=14.6,
            start_longitude=121.1,
            start_location_label="Depot",
            end_latitude=None,
            end_longitude=None,
            last_completed_at=None,
            last_completed_latitude=None,
            last_completed_longitude=None,
            break_starts_at=None,
            break_ends_at=None,
            max_open_cases=10,
            max_visits=5,
            shift_starts_at=datetime.combine(work_date, time(8), tzinfo=ZoneInfo("Asia/Manila")),
            shift_ends_at=datetime.combine(work_date, time(17), tzinfo=ZoneInfo("Asia/Manila")),
        )

        class AdvancingDateTime(datetime):
            @classmethod
            def now(cls, tz=None):
                return later_now.astimezone(tz) if tz else later_now.replace(tzinfo=None)

        class Solver:
            def solve(self, _payload):
                start = int(planned_at.timestamp())
                return {
                    "routes": [{
                        "vehicle": 7,
                        "steps": [
                            {"type": "start", "arrival": start, "duration": 0},
                            {"type": "job", "id": case.id, "arrival": start + 600, "duration": 600},
                            {"type": "end", "arrival": start + 1500, "duration": 1200},
                        ],
                    }],
                    "unassigned": [],
                }

        with patch("app.services.planning.datetime", AdvancingDateTime):
            outcomes = _run_component(
                [0, 1],
                {(14.5, 121.0): 0, (14.6, 121.1): 1},
                [(14.5, 121.0), (14.6, 121.1)],
                [[0, 600], [600, 0]],
                [[0, 5000], [5000, 0]],
                [case],
                [shift],
                {},
                {7: 0},
                Solver(),
                now=planned_at,
            )

        self.assertEqual(outcomes[0]["outcome"], "assigned")
        self.assertEqual(outcomes[0]["estimated_arrival_at"], planned_at.astimezone(timezone.utc) + timedelta(minutes=10))

    def test_vroom_break_before_first_job_does_not_double_count_travel(self):
        work_date = datetime.now(ZoneInfo("Asia/Manila")).date()
        planning_now = datetime.combine(work_date, time(11), tzinfo=ZoneInfo("Asia/Manila"))
        break_start = datetime.combine(work_date, time(12), tzinfo=ZoneInfo("Asia/Manila"))
        break_end = datetime.combine(work_date, time(13), tzinfo=ZoneInfo("Asia/Manila"))
        outbound_seconds = 1536
        return_seconds = 1649
        service_seconds = 3600
        break_start_epoch = int(break_start.timestamp())
        break_end_epoch = int(break_end.timestamp())
        case = SimpleNamespace(
            id=402,
            latitude=14.5,
            longitude=121.0,
            service_duration_seconds=service_seconds,
            priority="normal",
            region_code="1300000000",
            visit_not_before_at=None,
            visit_due_at=None,
            assigned_agent_id=None,
        )
        shift = SimpleNamespace(
            agent_id=7,
            work_date=work_date,
            region_code="1300000000",
            start_latitude=14.6,
            start_longitude=121.1,
            start_location_label="Depot",
            end_latitude=None,
            end_longitude=None,
            last_completed_at=None,
            last_completed_latitude=None,
            last_completed_longitude=None,
            break_starts_at=break_start.astimezone(timezone.utc),
            break_ends_at=break_end.astimezone(timezone.utc),
            max_open_cases=10,
            max_visits=5,
            shift_starts_at=datetime.combine(work_date, time(8), tzinfo=ZoneInfo("Asia/Manila")),
            shift_ends_at=datetime.combine(work_date, time(17), tzinfo=ZoneInfo("Asia/Manila")),
        )

        class Solver:
            def solve(self, _payload):
                start_arrival = break_start_epoch - outbound_seconds
                return {
                    "routes": [{
                        "vehicle": 7,
                        "steps": [
                            {"type": "start", "arrival": start_arrival, "duration": 0},
                            {"type": "break", "arrival": break_start_epoch, "duration": outbound_seconds, "waiting_time": 0, "service": break_end_epoch - break_start_epoch},
                            {"type": "job", "id": case.id, "arrival": break_end_epoch, "duration": outbound_seconds, "waiting_time": 0},
                            {"type": "end", "arrival": break_end_epoch + service_seconds + return_seconds, "duration": outbound_seconds + return_seconds},
                        ],
                    }],
                    "unassigned": [],
                }

        outcomes = _run_component(
            [0, 1],
            {(14.6, 121.1): 0, (14.5, 121.0): 1},
            [(14.6, 121.1), (14.5, 121.0)],
            [[0, outbound_seconds], [return_seconds, 0]],
            [[0, 12000], [13000, 0]],
            [case],
            [shift],
            {},
            {7: 1},
            Solver(),
            now=planning_now,
        )

        self.assertEqual(outcomes[0]["outcome"], "assigned")
        self.assertEqual(outcomes[0]["route_break_seconds"], break_end_epoch - break_start_epoch)

    def test_latest_completed_visit_is_current_shift_origin_and_next_shift_resets_to_depot(self):
        from types import SimpleNamespace

        work_date = datetime.now(ZoneInfo("Asia/Manila")).date()
        next_work_date = work_date + timedelta(days=1)
        current_now = datetime.combine(work_date, time(14), tzinfo=ZoneInfo("Asia/Manila"))
        completed_at = datetime.combine(work_date, time(11), tzinfo=ZoneInfo("Asia/Manila"))
        shift = SimpleNamespace(
            work_date=work_date,
            shift_starts_at=datetime.combine(work_date, time(8), tzinfo=ZoneInfo("Asia/Manila")),
            shift_ends_at=datetime.combine(work_date, time(17), tzinfo=ZoneInfo("Asia/Manila")),
            start_latitude=14.6,
            start_longitude=121.1,
            start_location_label="Configured depot",
            last_completed_at=completed_at,
            last_completed_latitude=14.7,
            last_completed_longitude=121.2,
        )

        self.assertEqual(
            _route_origin(shift, current_now),
            (14.7, 121.2, "Latest completed visit (estimated)"),
        )

        next_shift = SimpleNamespace(
            work_date=next_work_date,
            shift_starts_at=datetime.combine(next_work_date, time(8), tzinfo=ZoneInfo("Asia/Manila")),
            shift_ends_at=datetime.combine(next_work_date, time(17), tzinfo=ZoneInfo("Asia/Manila")),
            start_latitude=14.6,
            start_longitude=121.1,
            start_location_label="Configured depot",
            last_completed_at=completed_at,
            last_completed_latitude=14.7,
            last_completed_longitude=121.2,
        )
        next_now = datetime.combine(next_work_date, time(10), tzinfo=ZoneInfo("Asia/Manila"))
        self.assertEqual(
            _route_origin(next_shift, next_now),
            (14.6, 121.1, "Configured depot (assumed; no live location available)"),
        )

    def test_all_region_vehicle_uses_region_skills_and_validates_waiting_and_fixed_break(self):
        work_date = date(2026, 11, 4)
        shift_start = datetime(2026, 11, 4, 8, 0, tzinfo=timezone.utc)
        visit_start = datetime(2026, 11, 4, 8, 15, tzinfo=timezone.utc)
        break_start = datetime(2026, 11, 4, 12, 0, tzinfo=timezone.utc)
        break_end = datetime(2026, 11, 4, 13, 0, tzinfo=timezone.utc)
        case = SimpleNamespace(
            id=301,
            latitude=14.5,
            longitude=121.0,
            service_duration_seconds=2700,
            priority="normal",
            region_code="1300000000",
            visit_not_before_at=visit_start,
            visit_due_at=None,
            assigned_agent_id=None,
        )
        shift = SimpleNamespace(
            agent_id=7,
            work_date=work_date,
            region_code="ALL",
            start_latitude=14.6,
            start_longitude=121.1,
            start_location_label="Depot",
            end_latitude=None,
            end_longitude=None,
            last_completed_at=None,
            last_completed_latitude=None,
            last_completed_longitude=None,
            break_starts_at=break_start,
            break_ends_at=break_end,
            max_open_cases=10,
            max_visits=8,
            shift_starts_at=shift_start,
            shift_ends_at=datetime(2026, 11, 4, 17, 0, tzinfo=timezone.utc),
        )

        class Solver:
            payload = None

            def solve(self, payload):
                self.payload = payload
                return {
                    "routes": [{
                        "vehicle": 7,
                        "steps": [
                            {"type": "start", "arrival": int(shift_start.timestamp())},
                            {"type": "job", "id": case.id, "arrival": int(datetime(2026, 11, 4, 8, 10, tzinfo=timezone.utc).timestamp()), "waiting_time": 300},
                            {"type": "break", "arrival": int(datetime(2026, 11, 4, 11, 55, tzinfo=timezone.utc).timestamp()), "waiting_time": 300, "service": 3600},
                            {"type": "end", "arrival": int(datetime(2026, 11, 4, 13, 10, tzinfo=timezone.utc).timestamp())},
                        ],
                    }],
                    "unassigned": [],
                }

        solver = Solver()
        outcomes = _run_component(
            [0, 1],
            {(14.5, 121.0): 0, (14.6, 121.1): 1},
            [(14.5, 121.0), (14.6, 121.1)],
            [[0, 600], [600, 0]],
            [[0, 5000], [5000, 0]],
            [case],
            [shift],
            {},
            {7: 0},
            solver,
        )

        job = solver.payload["jobs"][0]
        vehicle = solver.payload["vehicles"][0]
        self.assertEqual(job["skills"], [_region_skill(case.region_code)])
        self.assertEqual(
            vehicle["skills"],
            [_region_skill(code) for code in sorted(catalog()["region_codes"])] + [1_000_007],
        )
        self.assertEqual(vehicle["breaks"], [{
            "id": 2_000_007,
            "time_windows": [[int(break_start.timestamp()), int(break_start.timestamp())]],
            "service": 3600,
        }])
        self.assertEqual(outcomes[0]["estimated_service_start_at"], visit_start)
        self.assertEqual(outcomes[0]["waiting_seconds"], 300)
        self.assertEqual(outcomes[0]["route_break_seconds"], 3600)

    def test_osrm_table_uses_osrm_axis_order_and_requests_both_cost_matrices(self):
        response = SimpleNamespace(
            raise_for_status=Mock(),
            json=Mock(return_value={
                "code": "Ok",
                "durations": [[0, 600], [650, 0]],
                "distances": [[0, 5000], [5200, 0]],
            }),
        )
        client = OSRMClient("http://router")
        client.client = SimpleNamespace(get=Mock(return_value=response))

        result = client.table([(14.5, 121.0), (14.6, 121.1)])

        request = client.client.get.call_args
        self.assertEqual(
            request.args[0],
            "http://router/table/v1/driving/121.000000,14.500000;121.100000,14.600000",
        )
        self.assertEqual(request.kwargs["params"], {"annotations": "duration,distance", "exclude": "ferry"})
        self.assertEqual(result["durations"][0][1], 600)
        self.assertEqual(result["distances"][0][1], 5000)

    def test_vroom_client_posts_custom_matrix_problem_and_checks_solver_code(self):
        payload = {
            "vehicles": [{"id": 7, "profile": "car", "start_index": 0}],
            "jobs": [{"id": 101, "location_index": 1}],
            "matrices": {"car": {"durations": [[0, 60], [60, 0]]}},
        }
        response = SimpleNamespace(
            raise_for_status=Mock(),
            json=Mock(return_value={"code": 0, "routes": [], "unassigned": [{"id": 101}]}),
        )
        client = VROOMClient("http://solver")
        client.client = SimpleNamespace(post=Mock(return_value=response))

        result = client.solve(payload)

        client.client.post.assert_called_once_with("http://solver/", json=payload)
        self.assertEqual(result["unassigned"], [{"id": 101}])

        response.json.return_value = {"code": 3, "error": "invalid input"}
        with self.assertRaisesRegex(RoutingUnavailable, "vroom_solver_failed"):
            client.solve(payload)

    def test_locked_agent_must_be_selected_for_the_run(self):
        with self.assertRaises(ValidationError):
            PlanningRunCreate(
                work_date="2026-11-04",
                region_code="1300000000",
                investigation_ids=[1],
                agent_ids=[7],
                locked_assignments=[{"investigation_id": 1, "agent_id": 9}],
            )

    def test_road_groups_never_contain_null_or_asymmetric_matrix_entries(self):
        durations = [
            [0, 10, None, None],
            [10, 0, None, None],
            [None, None, 0, 20],
            [None, None, 20, 0],
        ]
        distances = [
            [0, 100, None, None],
            [100, 0, None, None],
            [None, None, 0, 200],
            [None, None, 200, 0],
        ]
        groups = _connected_components(durations, distances)
        self.assertEqual(groups, [[0, 1], [2, 3]])
        for group in groups:
            for source in group:
                for target in group:
                    self.assertIsNotNone(durations[source][target])
                    self.assertIsNotNone(distances[source][target])

    def test_osrm_nearest_uses_one_request_per_coordinate_and_osrm_axis_order(self):
        client = OSRMClient("http://osrm")

        class Response:
            status_code = 200

            def raise_for_status(self):
                return None

            @staticmethod
            def json():
                return {"code": "Ok", "waypoints": [{"distance": 12}]}

        client.client = SimpleNamespace(get=Mock(return_value=Response()))
        coordinates = [(14.5, 121.0), (14.6, 121.1)]
        result = client.nearest_many(coordinates)
        self.assertEqual(len(result), 2)
        self.assertEqual(client.client.get.call_count, 2)
        requested_urls = [call.args[0] for call in client.client.get.call_args_list]
        self.assertIn("121.000000,14.500000", requested_urls[0] + requested_urls[1])
        self.assertIn("121.100000,14.600000", requested_urls[0] + requested_urls[1])

    def test_osrm_nearest_marks_no_segment_as_unroutable(self):
        client = OSRMClient("http://osrm")

        class Response:
            status_code = 400

            @staticmethod
            def json():
                return {"code": "NoSegment", "message": "No segment found"}

            def raise_for_status(self):
                raise AssertionError("NoSegment should be handled as an unroutable point")

        client.client = SimpleNamespace(get=Mock(return_value=Response()))
        result = client.nearest((14.5, 121.0))
        self.assertTrue(result["unroutable"])
        self.assertEqual(result["distance"], float("inf"))

    def test_vroom_payload_uses_absolute_time_window_pairs_and_completion_deadlines(self):
        case = SimpleNamespace(
            id=101,
            latitude=14.5,
            longitude=121.0,
            service_duration_seconds=2700,
            priority="urgent",
            region_code="1300000000",
            visit_not_before_at=datetime(2026, 11, 4, 9, 0, tzinfo=timezone.utc),
            visit_due_at=datetime(2026, 11, 4, 10, 0, tzinfo=timezone.utc),
            assigned_agent_id=None,
        )
        shift = SimpleNamespace(
            agent_id=7,
            work_date=date(2026, 11, 4),
            region_code="1300000000",
            start_latitude=14.6,
            start_longitude=121.1,
            start_location_label="Depot",
            end_latitude=None,
            end_longitude=None,
            last_completed_at=None,
            last_completed_latitude=None,
            last_completed_longitude=None,
            break_starts_at=None,
            break_ends_at=None,
            max_open_cases=10,
            max_visits=5,
            shift_starts_at=datetime(2026, 11, 4, 8, 0, tzinfo=timezone.utc),
            shift_ends_at=datetime(2026, 11, 4, 17, 0, tzinfo=timezone.utc),
        )

        class Solver:
            payload = None

            def solve(self, payload):
                self.payload = payload
                return {"routes": [], "unassigned": [{"id": 101}]}

        solver = Solver()
        _run_component(
            [0, 1],
            {(14.5, 121.0): 0, (14.6, 121.1): 1},
            [(14.5, 121.0), (14.6, 121.1)],
            [[0, 600], [650, 0]],
            [[0, 5000], [5200, 0]],
            [case],
            [shift],
            {},
            {7: 1},
            solver,
        )
        job = solver.payload["jobs"][0]
        vehicle = solver.payload["vehicles"][0]
        self.assertEqual(job["time_windows"], [[
            int(datetime(2026, 11, 4, 9, 0, tzinfo=timezone.utc).timestamp()),
            int(datetime(2026, 11, 4, 9, 15, tzinfo=timezone.utc).timestamp()),
        ]])
        self.assertEqual(vehicle["time_window"], [
            int(datetime(2026, 11, 4, 8, 0, tzinfo=timezone.utc).timestamp()),
            int(datetime(2026, 11, 4, 17, 0, tzinfo=timezone.utc).timestamp()),
        ])

    def test_vroom_vehicle_never_exceeds_configured_daily_visit_limit(self):
        cases = [
            SimpleNamespace(
                id=case_id,
                latitude=14.5,
                longitude=121.0,
                service_duration_seconds=2700,
                priority="normal",
                region_code="1300000000",
                visit_not_before_at=None,
                visit_due_at=None,
                assigned_agent_id=7,
            )
            for case_id in range(101, 107)
        ]
        shift = SimpleNamespace(
            agent_id=7,
            work_date=date(2026, 11, 4),
            region_code="1300000000",
            start_latitude=14.6,
            start_longitude=121.1,
            start_location_label="Depot",
            end_latitude=None,
            end_longitude=None,
            last_completed_at=None,
            last_completed_latitude=None,
            last_completed_longitude=None,
            break_starts_at=None,
            break_ends_at=None,
            max_open_cases=5,
            max_visits=4,
            shift_starts_at=datetime(2026, 11, 4, 8, 0, tzinfo=timezone.utc),
            shift_ends_at=datetime(2026, 11, 4, 17, 0, tzinfo=timezone.utc),
        )

        class Solver:
            payload = None

            def solve(self, payload):
                self.payload = payload
                return {"routes": [], "unassigned": [{"id": case.id} for case in cases]}

        solver = Solver()
        _run_component(
            [0, 1],
            {(14.5, 121.0): 0, (14.6, 121.1): 1},
            [(14.5, 121.0), (14.6, 121.1)],
            [[0, 600], [650, 0]],
            [[0, 5000], [5200, 0]],
            cases,
            [shift],
            {case.id: 7 for case in cases},
            {7: 6},
            solver,
        )

        self.assertEqual(solver.payload["vehicles"][0]["max_tasks"], shift.max_visits)


class GeocodingTests(unittest.TestCase):
    def test_search_is_country_restricted_and_discards_invalid_points(self):
        investigation = SimpleNamespace(
            address_display="42 Sample Street, Quezon City",
            region_code="1300000000",
        )
        response = SimpleNamespace(
            raise_for_status=Mock(),
            json=Mock(return_value=[
                {"lat": "14.6507", "lon": "121.0494", "display_name": "Sample Street", "osm_type": "way", "osm_id": 123},
                {"lat": "NaN", "lon": "121.0494", "display_name": "Invalid", "osm_type": "node", "osm_id": 456},
            ]),
        )
        with patch("app.services.geocoding.httpx.get", return_value=response) as get:
            candidates = suggest_locations(investigation)
        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0].provider_ref, "way/123")
        request_params = get.call_args.kwargs["params"]
        self.assertEqual(request_params["countrycodes"], "ph")
        self.assertNotIn("Fictional Subject", request_params["q"])

    def test_unexpected_geocoder_response_is_sanitized(self):
        response = SimpleNamespace(raise_for_status=Mock(), json=Mock(return_value={"error": "bad query"}))
        with patch("app.services.geocoding.httpx.get", return_value=response):
            with self.assertRaisesRegex(RuntimeError, "geocoder_unavailable"):
                suggest_locations(SimpleNamespace(address_display="Sample", region_code="1300000000"))


class AutomaticPublicationTests(unittest.TestCase):
    def test_vroom_selects_the_feasible_available_agent_and_publishes_that_route(self):
        from app.models.assignment import InvestigationAssignment
        from app.services import planning as planning_service

        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(engine)
        work_date = datetime(2026, 11, 4, tzinfo=timezone.utc).date()

        class Router:
            def __init__(self):
                pass

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
                    "duration": 1200,
                }

            @staticmethod
            def close():
                pass

        class Solver:
            last_payload = None

            def solve(self, payload):
                Solver.last_payload = payload
                return {
                    "routes": [{
                        "vehicle": agent_b_id,
                        "steps": [
                            {"type": "start", "arrival": int(datetime(2026, 11, 4, 8, tzinfo=timezone.utc).timestamp())},
                            {"type": "job", "id": case_id, "arrival": int(datetime(2026, 11, 4, 11, tzinfo=timezone.utc).timestamp())},
                            {"type": "end", "arrival": int(datetime(2026, 11, 4, 12, 10, tzinfo=timezone.utc).timestamp())},
                        ],
                    }],
                    "unassigned": [],
                }

            @staticmethod
            def close():
                pass

        with Session(engine) as db:
            supervisor = User(name="Planner", email="planner-choice@example.test", password="hash", role="supervisor")
            agent_a = User(name="Short Shift", email="agent-short@example.test", password="hash", role="agent")
            agent_b = User(name="Long Shift", email="agent-long@example.test", password="hash", role="agent")
            unavailable_agent = User(name="Unavailable", email="agent-unavailable@example.test", password="hash", role="agent")
            db.add_all([supervisor, agent_a, agent_b, unavailable_agent])
            db.flush()
            agent_b_id = agent_b.id
            case = Investigation(
                reference_number="INV-PLAN-CHOICE",
                first_name="Fictional",
                last_name="Case",
                region_code="1300000000",
                latitude=14.5,
                longitude=121.0,
                location_source="manual",
                location_confirmed_at=datetime(2026, 11, 1, tzinfo=timezone.utc),
                **cells_for_point(14.5, 121.0),
                status="pending",
                priority="urgent",
                visit_not_before_at=datetime(2026, 11, 4, 11, tzinfo=timezone.utc),
                visit_due_at=datetime(2026, 11, 4, 12, 30, tzinfo=timezone.utc),
            )
            db.add(case)
            db.flush()
            case_id = case.id
            shifts = [
                AgentShift(
                    agent_id=agent_a.id,
                    work_date=work_date,
                    region_code="1300000000",
                    is_available=True,
                    shift_starts_at=datetime(2026, 11, 4, 8, tzinfo=timezone.utc),
                    shift_ends_at=datetime(2026, 11, 4, 10, tzinfo=timezone.utc),
                    start_latitude=14.6,
                    start_longitude=121.1,
                    max_visits=8,
                    max_open_cases=10,
                ),
                AgentShift(
                    agent_id=agent_b.id,
                    work_date=work_date,
                    region_code="1300000000",
                    is_available=True,
                    shift_starts_at=datetime(2026, 11, 4, 8, tzinfo=timezone.utc),
                    shift_ends_at=datetime(2026, 11, 4, 14, tzinfo=timezone.utc),
                    start_latitude=14.7,
                    start_longitude=121.2,
                    max_visits=5,
                    max_open_cases=10,
                ),
                AgentShift(
                    agent_id=unavailable_agent.id,
                    work_date=work_date,
                    region_code="1300000000",
                    is_available=False,
                    shift_starts_at=datetime(2026, 11, 4, 8, tzinfo=timezone.utc),
                    shift_ends_at=datetime(2026, 11, 4, 17, tzinfo=timezone.utc),
                    start_latitude=14.8,
                    start_longitude=121.3,
                    max_visits=5,
                    max_open_cases=10,
                ),
            ]
            db.add_all(shifts)
            with patch("app.workers.tasks.optimize_planning_run.apply_async"):
                run = planning_service.queue_automatic_planning(
                    db, "1300000000", supervisor, work_date
                )
            self.assertIsNotNone(run)

            with patch.object(planning_service, "OSRMClient", Router), patch.object(planning_service, "VROOMClient", Solver):
                execute_run(db, run.id)
            db.refresh(run)
            item = db.query(PlanningItem).filter_by(planning_run_id=run.id).one()
            payload = planning_service.run_response(db, run)

            vehicle_ids = {vehicle["id"] for vehicle in Solver.last_payload["vehicles"]}
            job = Solver.last_payload["jobs"][0]
            self.assertEqual(run.status, "ready")
            self.assertEqual(set(run.agent_ids), {agent_a.id, agent_b_id})
            self.assertEqual(vehicle_ids, {agent_a.id, agent_b_id})
            self.assertEqual(job["priority"], 100)
            self.assertEqual(job["time_windows"], [[
                int(datetime(2026, 11, 4, 11, tzinfo=timezone.utc).timestamp()),
                int(datetime(2026, 11, 4, 11, 45, tzinfo=timezone.utc).timestamp()),
            ]])
            self.assertEqual(item.outcome, "assigned")
            self.assertEqual(item.agent_id, agent_b_id)
            self.assertEqual(payload["items"][0]["agent_id"], agent_b_id)
            self.assertIsNone(case.assigned_agent_id)
            self.assertEqual(
                db.query(InvestigationAssignment).filter_by(investigation_id=case_id, is_active=True).count(),
                0,
            )
            applied = apply_run(db, run.id, run.result_digest, supervisor)
            self.assertEqual(applied.status, "applied")
            self.assertEqual(db.get(Investigation, case_id).assigned_agent_id, agent_b_id)
            assignment = db.query(InvestigationAssignment).filter_by(investigation_id=case_id, is_active=True).one()
            self.assertEqual(assignment.assignment_source, "automatic")
        engine.dispose()

    def test_mutation_during_external_optimization_prevents_ready_preview(self):
        from app.services import planning as planning_service

        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(engine)
        work_date = datetime(2026, 11, 4, tzinfo=timezone.utc).date()
        with Session(engine) as db:
            supervisor = User(name="Planner", email="planner-race@example.test", password="hash", role="supervisor")
            agent = User(name="Field Agent", email="agent-race@example.test", password="hash", role="agent")
            db.add_all([supervisor, agent])
            db.flush()
            cells = cells_for_point(14.5, 121.0)
            case = Investigation(
                reference_number="INV-PLAN-RACE-001",
                first_name="Fictional",
                last_name="Case",
                region_code="1300000000",
                latitude=14.5,
                longitude=121.0,
                location_source="manual",
                location_confirmed_at=datetime(2026, 11, 1, tzinfo=timezone.utc),
                h3_r7=cells["h3_r7"], h3_r8=cells["h3_r8"], h3_r9=cells["h3_r9"],
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
                start_latitude=14.6,
                start_longitude=121.1,
                max_visits=4,
                max_open_cases=10,
            )
            db.add_all([case, shift])
            db.flush()
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
            expected_digest = run.input_digest
            run.status = "running"
            db.commit()
            case.priority = "urgent"
            db.commit()

            saved = _record_ready_run(
                db,
                run,
                expected_digest,
                [case],
                [shift],
                [agent],
                {},
                {case.id: ("unassigned", "no_feasible_route_under_constraints")},
                {},
            )
            db.refresh(run)
            self.assertFalse(saved)
            self.assertEqual(run.status, "stale")
            self.assertEqual(run.error_code, "inputs_changed")

    def test_road_snap_exclusion_is_saved_as_an_unassigned_preview_item(self):
        from unittest.mock import patch

        from app.models.planning import AgentShift, PlanningItem, PlanningRun
        from app.services import planning as planning_service

        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(engine)
        work_date = datetime(2026, 11, 4, tzinfo=timezone.utc).date()

        class Router:
            def __init__(self):
                pass

            @staticmethod
            def nearest_many(coordinates):
                return [
                    {"distance": 3000 if coordinate == (14.5, 121.0) else 30}
                    for coordinate in coordinates
                ]

            @staticmethod
            def table(_coordinates):
                raise AssertionError("Unsnappable cases should not be sent to the route matrix")

            @staticmethod
            def close():
                pass

        class Solver:
            def __init__(self):
                pass

            def solve(self, _payload):
                raise AssertionError("No jobs should be sent to VROOM")

            @staticmethod
            def close():
                pass

        with Session(engine) as db:
            supervisor = User(name="Planner", email="planner@example.test", password="hash", role="supervisor")
            agent = User(name="Field Agent", email="agent@example.test", password="hash", role="agent")
            db.add_all([supervisor, agent])
            db.flush()
            case = Investigation(
                reference_number="INV-PLAN-SNAP-001",
                first_name="Fictional",
                last_name="Case",
                region_code="1300000000",
                latitude=14.5,
                longitude=121.0,
                location_source="manual",
                location_confirmed_at=datetime(2026, 11, 1, tzinfo=timezone.utc),
                h3_r7=cells_for_point(14.5, 121.0)["h3_r7"],
                h3_r8=cells_for_point(14.5, 121.0)["h3_r8"],
                h3_r9=cells_for_point(14.5, 121.0)["h3_r9"],
                status="pending",
                priority="normal",
            )
            db.add(case)
            db.flush()
            db.add(AgentShift(
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
            ))
            db.flush()
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
            with patch.object(planning_service, "OSRMClient", Router), patch.object(planning_service, "VROOMClient", Solver):
                execute_run(db, run.id)
            db.refresh(run)
            item = db.query(PlanningItem).filter_by(planning_run_id=run.id).one()
            self.assertEqual(run.status, "ready")
            self.assertEqual(item.outcome, "unassigned")
            self.assertEqual(item.reason, "road_snap_too_far")
            self.assertIsNone(item.agent_id)
            self.assertEqual(db.query(PlanningRun).filter_by(status="failed").count(), 0)

    def test_full_open_case_capacity_publishes_complete_unassigned_result_without_assignment(self):
        from app.models.assignment import InvestigationAssignment
        from app.models.planning import PlanningItem
        from app.services import planning as planning_service

        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(engine)
        work_date = datetime(2026, 11, 4, tzinfo=timezone.utc).date()
        with Session(engine) as db:
            supervisor = User(name="Planner", email="planner-capacity@example.test", password="hash", role="supervisor")
            agent = User(name="Field Agent", email="agent-capacity@example.test", password="hash", role="agent")
            db.add_all([supervisor, agent])
            db.flush()
            existing = Investigation(
                reference_number="INV-PLAN-CAP-EXISTING",
                first_name="Fictional",
                last_name="Existing",
                region_code="1300000000",
                status="assigned",
                priority="normal",
                assigned_agent_id=agent.id,
            )
            cells = cells_for_point(14.5, 121.0)
            pending = Investigation(
                reference_number="INV-PLAN-CAP-PENDING",
                first_name="Fictional",
                last_name="Pending",
                region_code="1300000000",
                latitude=14.5,
                longitude=121.0,
                location_source="manual",
                location_confirmed_at=datetime(2026, 11, 1, tzinfo=timezone.utc),
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
                start_latitude=14.6,
                start_longitude=121.1,
                max_visits=4,
                max_open_cases=1,
            )
            db.add_all([existing, pending, shift])
            db.flush()
            run = planning_service.create_run(
                db,
                PlanningRunCreate(
                    work_date=work_date,
                    region_code="1300000000",
                    investigation_ids=[pending.id],
                    agent_ids=[agent.id],
                ),
                supervisor,
            )

            execute_run(db, run.id)

            db.refresh(run)
            item = db.query(PlanningItem).filter_by(planning_run_id=run.id).one()
            self.assertEqual(run.status, "ready")
            self.assertEqual(item.outcome, "unassigned")
            self.assertEqual(item.reason, "agent_open_case_limit")
            self.assertIsNone(item.agent_id)
            run.auto_publish = True
            db.commit()
            applied = planning_service.apply_run(db, run.id, run.result_digest, supervisor)
            self.assertEqual(applied.status, "applied")
            self.assertIsNone(db.get(Investigation, pending.id).assigned_agent_id)
            self.assertEqual(
                db.query(InvestigationAssignment).filter_by(
                    investigation_id=pending.id, is_active=True
                ).count(),
                0,
            )
        engine.dispose()

    def test_worker_result_is_only_published_for_automatic_runs_and_is_idempotent(self):
        from unittest.mock import patch

        from app.models.assignment import InvestigationAssignment
        from app.services import planning as planning_service
        from app.services.investigation import assign_investigation

        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(engine)
        work_date = datetime(2026, 11, 4, tzinfo=timezone.utc).date()

        class Router:
            def __init__(self):
                pass

            @staticmethod
            def nearest_many(coordinates):
                return [{"distance": 30} for _ in coordinates]

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
            def solve(payload):
                return {
                    "routes": [{
                        "vehicle": 2,
                        "steps": [
                            {"type": "start", "arrival": int(datetime(2026, 11, 4, 0, tzinfo=timezone.utc).timestamp())},
                            {"type": "job", "id": case.id, "arrival": int(datetime(2026, 11, 4, 0, 10, tzinfo=timezone.utc).timestamp())},
                            {"type": "end", "arrival": int(datetime(2026, 11, 4, 1, 5, tzinfo=timezone.utc).timestamp())},
                        ],
                    }],
                    "unassigned": [],
                }

            @staticmethod
            def close():
                pass

        with Session(engine) as db:
            supervisor = User(name="Planner", email="planner@example.test", password="hash", role="supervisor")
            agent = User(name="Field Agent", email="agent@example.test", password="hash", role="agent")
            db.add_all([supervisor, agent])
            db.flush()
            case = Investigation(
                reference_number="INV-PLAN-001",
                first_name="Fictional",
                last_name="Case",
                region_code="1300000000",
                latitude=14.5,
                longitude=121.0,
                location_source="manual",
                location_confirmed_at=datetime(2026, 11, 1, tzinfo=timezone.utc),
                h3_r7=cells_for_point(14.5, 121.0)["h3_r7"],
                h3_r8=cells_for_point(14.5, 121.0)["h3_r8"],
                h3_r9=cells_for_point(14.5, 121.0)["h3_r9"],
                status="pending",
                priority="normal",
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
            run_id = run.id
            case_id = case.id
            agent_id = agent.id
            supervisor_id = supervisor.id

            with patch.object(planning_service, "OSRMClient", Router), patch.object(planning_service, "VROOMClient", Solver):
                execute_run(db, run_id)

            ready = db.query(PlanningRun).filter(PlanningRun.id == run_id).one()
            self.assertEqual(ready.status, "ready")
            self.assertIsNotNone(ready.result_digest)
            digest = ready.result_digest

            with self.assertRaisesRegex(PlanningConflict, "automatic_publication_required"):
                apply_run(db, run_id, digest, db.get(User, supervisor_id))
            ready.auto_publish = True
            db.commit()
            applied = apply_run(db, run_id, digest, db.get(User, supervisor_id))
            self.assertEqual(applied.status, "applied")
            assigned_case = db.get(Investigation, case_id)
            self.assertEqual(assigned_case.status, "assigned")
            self.assertEqual(assigned_case.assigned_agent_id, agent_id)
            self.assertEqual(db.query(InvestigationAssignment).filter_by(investigation_id=case_id, is_active=True).count(), 1)
            self.assertEqual(db.get(AgentShift, shift.id).current_planning_run_id, run_id)

            repeated = apply_run(db, run_id, digest, db.get(User, supervisor_id))
            self.assertEqual(repeated.status, "applied")
            self.assertEqual(db.query(InvestigationAssignment).filter_by(investigation_id=case_id, is_active=True).count(), 1)

            stale_run = planning_service.create_run(
                db,
                PlanningRunCreate(
                    work_date=work_date,
                    region_code="1300000000",
                    investigation_ids=[case_id],
                    agent_ids=[agent_id],
                ),
                db.get(User, supervisor_id),
            )
            shift = db.get(AgentShift, shift.id)
            shift.max_visits += 1
            db.commit()
            with patch.object(planning_service, "OSRMClient", Router), patch.object(planning_service, "VROOMClient", Solver):
                execute_run(db, stale_run.id)
            db.refresh(stale_run)
            self.assertEqual(stale_run.status, "stale")
            self.assertEqual(db.query(InvestigationAssignment).filter_by(investigation_id=case_id, is_active=True).count(), 1)

            assignment_change_run = planning_service.create_run(
                db,
                PlanningRunCreate(
                    work_date=work_date,
                    region_code="1300000000",
                    investigation_ids=[case_id],
                    agent_ids=[agent_id],
                ),
                db.get(User, supervisor_id),
            )
            with patch.object(planning_service, "OSRMClient", Router), patch.object(planning_service, "VROOMClient", Solver):
                execute_run(db, assignment_change_run.id)
            db.refresh(assignment_change_run)
            self.assertEqual(assignment_change_run.status, "ready")
            today = datetime.now(ZoneInfo("Asia/Manila")).date()
            today_shift_start = datetime.combine(today, time(8)).replace(
                tzinfo=ZoneInfo("Asia/Manila")
            ).astimezone(timezone.utc)
            db.add(AgentShift(
                agent_id=agent_id,
                work_date=today,
                region_code="1300000000",
                is_available=True,
                shift_starts_at=today_shift_start,
                shift_ends_at=today_shift_start + timedelta(hours=9),
                start_latitude=14.6,
                start_longitude=121.1,
                max_visits=10,
                max_open_cases=20,
            ))
            db.commit()
            assign_investigation(
                db,
                db.get(Investigation, case_id),
                db.get(User, agent_id),
                db.get(User, supervisor_id),
                "Supervisor reassignment",
            )
            db.refresh(assignment_change_run)
            self.assertEqual(assignment_change_run.status, "stale")
            self.assertEqual(assignment_change_run.error_code, "assignment_changed")
            # Repeating the same assignment no longer invalidates the already
            # published route; only the newly prepared preview is stale.
            self.assertEqual(db.get(AgentShift, shift.id).current_planning_run_id, run.id)

            shift_change_run = planning_service.create_run(
                db,
                PlanningRunCreate(
                    work_date=work_date,
                    region_code="1300000000",
                    investigation_ids=[case_id],
                    agent_ids=[agent_id],
                ),
                db.get(User, supervisor_id),
            )
            current_shift = db.get(AgentShift, shift.id)
            planning_service.set_agent_shift(
                db,
                agent_id,
                AgentShiftInput(
                    work_date=work_date,
                    region_code=current_shift.region_code,
                    is_available=False,
                    shift_starts_at=datetime(2026, 11, 4, 0, tzinfo=timezone.utc),
                    shift_ends_at=datetime(2026, 11, 4, 9, tzinfo=timezone.utc),
                    start_latitude=current_shift.start_latitude,
                    start_longitude=current_shift.start_longitude,
                    end_latitude=current_shift.end_latitude,
                    end_longitude=current_shift.end_longitude,
                    max_visits=current_shift.max_visits,
                    max_open_cases=current_shift.max_open_cases,
                ),
            )
            db.refresh(shift_change_run)
            self.assertEqual(shift_change_run.status, "stale")
            self.assertEqual(shift_change_run.error_code, "shift_changed")
            self.assertIsNone(db.get(AgentShift, shift.id).current_planning_run_id)

if __name__ == "__main__":
    unittest.main()
