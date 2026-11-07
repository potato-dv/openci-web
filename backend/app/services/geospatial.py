from math import asin, cos, isfinite, radians, sin, sqrt

import h3


DEFAULT_SERVICE_RADIUS_METRES = 10_000
EARTH_MEAN_RADIUS_METRES = 6_371_008.8


def validate_coordinates(latitude: float, longitude: float) -> None:
    if not isfinite(latitude) or not isfinite(longitude):
        raise ValueError("Coordinates must be finite numbers")
    if not -90 <= latitude <= 90 or not -180 <= longitude <= 180:
        raise ValueError("Coordinates must be valid WGS84 latitude and longitude")


def distance_metres(
    latitude_a: float,
    longitude_a: float,
    latitude_b: float,
    longitude_b: float,
) -> float:
    """Return great-circle distance between two WGS84 points in metres."""
    validate_coordinates(latitude_a, longitude_a)
    validate_coordinates(latitude_b, longitude_b)
    lat_a, lat_b = radians(latitude_a), radians(latitude_b)
    delta_lat = lat_b - lat_a
    delta_lon = radians(longitude_b - longitude_a)
    haversine = (
        sin(delta_lat / 2) ** 2
        + cos(lat_a) * cos(lat_b) * sin(delta_lon / 2) ** 2
    )
    return 2 * EARTH_MEAN_RADIUS_METRES * asin(sqrt(min(1.0, haversine)))


def cells_for_point(latitude: float, longitude: float) -> dict[str, str]:
    validate_coordinates(latitude, longitude)
    return {
        f"h3_r{resolution}": h3.latlng_to_cell(latitude, longitude, resolution)
        for resolution in (7, 8, 9)
    }


def neighboring_cells(cell: str, radius: int = 1) -> set[str]:
    if radius < 0 or radius > 3:
        raise ValueError("H3 search radius must be between 0 and 3")
    return set(h3.grid_disk(cell, radius))
