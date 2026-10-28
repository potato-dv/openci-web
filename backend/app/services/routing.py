from concurrent.futures import ThreadPoolExecutor

from math import isfinite

import httpx

from app.config.settings import (
    GEOSPATIAL_HTTP_TIMEOUT_SECONDS,
    OSRM_URL,
    VROOM_URL,
)


class RoutingUnavailable(RuntimeError):
    pass


def valid_route_geometry(geometry) -> bool:
    if not isinstance(geometry, dict) or geometry.get("type") != "LineString":
        return False
    points = geometry.get("coordinates")
    if not isinstance(points, list) or len(points) < 2:
        return False
    return all(
        isinstance(point, (list, tuple)) and len(point) == 2
        and all(not isinstance(value, bool) and isinstance(value, (int, float)) and isfinite(value) for value in point)
        and -180 <= point[0] <= 180 and -90 <= point[1] <= 90
        for point in points
    )


class OSRMClient:
    def __init__(self, base_url: str = OSRM_URL):
        self.base_url = base_url.rstrip("/")
        self.client = httpx.Client(
            timeout=GEOSPATIAL_HTTP_TIMEOUT_SECONDS,
            transport=httpx.HTTPTransport(retries=2),
        )

    @staticmethod
    def _coordinates_path(coordinates: list[tuple[float, float]]) -> str:
        # OSRM coordinate order is longitude,latitude (H3 takes the reverse).
        return ";".join(f"{longitude:.6f},{latitude:.6f}" for latitude, longitude in coordinates)

    def nearest(self, coordinate: tuple[float, float]) -> dict:
        return self.nearest_many([coordinate])[0]

    def nearest_many(self, coordinates: list[tuple[float, float]]) -> list[dict]:
        # OSRM Nearest takes one input coordinate per request. Keep a bounded
        # pool so the 80-point run limit does not turn into serial HTTP latency.
        def snap(coordinate: tuple[float, float]) -> dict:
            response = self.client.get(
                f"{self.base_url}/nearest/v1/driving/{self._coordinates_path([coordinate])}",
                params={"number": 1},
            )
            if response.status_code >= 400:
                try:
                    error_payload = response.json()
                except ValueError:
                    error_payload = {}
                if error_payload.get("code") == "NoSegment":
                    return {"distance": float("inf"), "unroutable": True}
            response.raise_for_status()
            payload = response.json()
            waypoints = payload.get("waypoints", [])
            if payload.get("code") == "NoSegment":
                return {"distance": float("inf"), "unroutable": True}
            if payload.get("code") != "Ok" or len(waypoints) != 1:
                raise RoutingUnavailable("osrm_snap_failed")
            return waypoints[0]

        try:
            with ThreadPoolExecutor(max_workers=min(8, max(1, len(coordinates)))) as pool:
                return list(pool.map(snap, coordinates))
        except (httpx.HTTPError, ValueError) as error:
            raise RoutingUnavailable("osrm_snap_failed") from error

    def table(self, coordinates: list[tuple[float, float]]) -> dict:
        try:
            response = self.client.get(
                f"{self.base_url}/table/v1/driving/{self._coordinates_path(coordinates)}",
                params={"annotations": "duration,distance", "exclude": "ferry"},
            )
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, ValueError) as error:
            raise RoutingUnavailable("osrm_table_unavailable") from error
        if payload.get("code") != "Ok":
            raise RoutingUnavailable("osrm_table_failed")
        return payload

    def route(self, coordinates: list[tuple[float, float]]) -> dict:
        if len(coordinates) < 2:
            raise RoutingUnavailable("osrm_route_shape_invalid")
        try:
            response = self.client.get(
                f"{self.base_url}/route/v1/driving/{self._coordinates_path(coordinates)}",
                params={"overview": "full", "geometries": "geojson", "steps": "false", "exclude": "ferry", "continue_straight": "false"},
            )
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, ValueError) as error:
            raise RoutingUnavailable("osrm_route_unavailable") from error
        if not isinstance(payload, dict) or payload.get("code") != "Ok" or not isinstance(payload.get("routes"), list) or not payload["routes"]:
            raise RoutingUnavailable("osrm_route_failed")
        result = payload["routes"][0]
        if not isinstance(result, dict):
            raise RoutingUnavailable("osrm_route_shape_invalid")
        geometry = result.get("geometry", {})
        if not valid_route_geometry(geometry):
            raise RoutingUnavailable("osrm_route_shape_invalid")
        for key in ("distance", "duration"):
            value = result.get(key)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not isfinite(value) or value < 0:
                raise RoutingUnavailable("osrm_route_shape_invalid")
        return result

    def close(self) -> None:
        self.client.close()


class VROOMClient:
    def __init__(self, base_url: str = VROOM_URL):
        self.base_url = base_url.rstrip("/")
        self.client = httpx.Client(
            timeout=GEOSPATIAL_HTTP_TIMEOUT_SECONDS * 4,
            transport=httpx.HTTPTransport(retries=2),
        )

    def solve(self, payload: dict) -> dict:
        try:
            response = self.client.post(f"{self.base_url}/", json=payload)
            response.raise_for_status()
            result = response.json()
        except (httpx.HTTPError, ValueError) as error:
            raise RoutingUnavailable("vroom_unavailable") from error
        if not isinstance(result, dict) or result.get("code") != 0:
            raise RoutingUnavailable("vroom_solver_failed")
        if not isinstance(result.get("routes"), list) or not isinstance(result.get("unassigned"), list):
            raise RoutingUnavailable("vroom_solution_shape_invalid")
        return result

    def close(self) -> None:
        self.client.close()

