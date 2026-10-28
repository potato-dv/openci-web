from math import isfinite

import h3


def validate_coordinates(latitude: float, longitude: float) -> None:
    if not isfinite(latitude) or not isfinite(longitude):
        raise ValueError("Coordinates must be finite numbers")
    if not -90 <= latitude <= 90 or not -180 <= longitude <= 180:
        raise ValueError("Coordinates must be valid WGS84 latitude and longitude")


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
