import unittest
from unittest.mock import patch

from fastapi import HTTPException

from app.routes.investigation import router as investigation_router
from app.routes.planning import router as planning_router
from app.utils.features import require_planning_enabled


class PlanningFeatureFlagTests(unittest.TestCase):
    def test_disabled_flag_rejects_planning_requests(self):
        with patch("app.utils.features.PLANNING_ENABLED", False):
            with self.assertRaises(HTTPException) as raised:
                require_planning_enabled()
        self.assertEqual(raised.exception.status_code, 503)
        self.assertEqual(raised.exception.detail, "Assignment planning is disabled")

    def test_flag_is_attached_to_planning_and_location_routes(self):
        self.assertTrue(any(
            dependency.dependency is require_planning_enabled
            for dependency in planning_router.dependencies
        ))
        location_routes = [
            route for route in investigation_router.routes
            if getattr(route, "path", "").endswith("/location")
            or getattr(route, "path", "").endswith("/geocode-suggestions")
        ]
        self.assertEqual(len(location_routes), 3)
        for route in location_routes:
            self.assertTrue(any(
                dependency.call is require_planning_enabled
                for dependency in route.dependant.dependencies
            ))


if __name__ == "__main__":
    unittest.main()
