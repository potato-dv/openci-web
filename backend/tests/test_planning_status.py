import unittest
from unittest.mock import patch

import httpx
from app.services import planning_status


class PlanningStatusTests(unittest.TestCase):
    def tearDown(self):
        planning_status.clear_planning_status_cache()

    @patch("app.services.planning_status.OSRM_DATASET_VERSION", "philippines-2026-10-23")
    @patch("app.services.planning_status._vroom_ready", return_value=True)
    @patch("app.services.planning_status._osrm_ready", return_value=True)
    @patch("app.services.planning_status._worker_ready", return_value=True)
    def test_status_is_cached_for_repeated_reads(self, worker, osrm, vroom):
        first = planning_status.get_planning_service_status()
        second = planning_status.get_planning_service_status()

        self.assertTrue(first["ready"])
        self.assertIs(first, second)
        worker.assert_called_once()
        osrm.assert_called_once()
        vroom.assert_called_once()

        planning_status.get_planning_service_status(force=True)
        self.assertEqual(worker.call_count, 2)
        self.assertEqual(osrm.call_count, 2)
        self.assertEqual(vroom.call_count, 2)

    @patch("app.services.planning_status.OSRM_DATASET_VERSION", "unconfigured")
    @patch("app.services.planning_status._vroom_ready", return_value=False)
    @patch("app.services.planning_status._osrm_ready", return_value=False)
    @patch("app.services.planning_status._worker_ready", return_value=False)
    def test_status_reports_every_blocking_dependency(self, _worker, _osrm, _vroom):
        result = planning_status.get_planning_service_status(force=True)

        self.assertFalse(result["ready"])
        self.assertIsNone(result["dataset_version"])
        self.assertEqual(
            result["blocking_reasons"],
            [
                "dataset_unconfigured",
                "worker_unavailable",
                "osrm_unavailable",
                "vroom_unavailable",
            ],
        )

    @patch("app.services.planning_status.OSRM_DATASET_VERSION", "philippines-2026-10-23")
    @patch("app.services.planning_status._vroom_ready", return_value=True)
    @patch("app.services.planning_status._osrm_ready", return_value=True)
    @patch("app.services.planning_status._worker_ready", return_value=True)
    @patch("app.services.planning_status.monotonic", side_effect=[100.0, 100.0, 109.9, 110.1, 110.1])
    def test_status_cache_expires_after_ten_seconds(
        self, _clock, worker, osrm, vroom
    ):
        planning_status.get_planning_service_status()
        planning_status.get_planning_service_status()
        planning_status.get_planning_service_status()

        self.assertEqual(worker.call_count, 2)
        self.assertEqual(osrm.call_count, 2)
        self.assertEqual(vroom.call_count, 2)

    @patch("app.services.planning_status.httpx.get")
    def test_http_probe_timeouts_are_reported_as_unavailable(self, get):
        request = httpx.Request("GET", "http://routing.test/health")
        get.side_effect = httpx.ReadTimeout("probe timed out", request=request)

        self.assertFalse(planning_status._osrm_ready())
        self.assertFalse(planning_status._vroom_ready())
        self.assertEqual(get.call_count, 2)
        self.assertTrue(
            all(
                call.kwargs["timeout"] == planning_status.PROBE_TIMEOUT_SECONDS
                for call in get.call_args_list
            )
        )

if __name__ == "__main__":
    unittest.main()
