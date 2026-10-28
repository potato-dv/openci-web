import httpx

from app.config.settings import GEOSPATIAL_HTTP_TIMEOUT_SECONDS, NOMINATIM_URL
from app.models.investigation import Investigation
from app.schemas.planning import GeocodeCandidate
from app.services.geospatial import validate_coordinates


def suggest_locations(investigation: Investigation) -> list[GeocodeCandidate]:
    address = investigation.address_display.strip()
    if investigation.region_code:
        address = f"{address}, Philippines"

    return search_locations(address)


def search_locations(address: str) -> list[GeocodeCandidate]:
    try:
        response = httpx.get(
            f"{NOMINATIM_URL.rstrip('/')}/search",
            params={
                "q": address,
                "countrycodes": "ph",
                "format": "jsonv2",
                "addressdetails": 1,
                "limit": 5,
            },
            headers={"User-Agent": "OpenCI/1.0 (self-hosted geocoding)"},
            timeout=GEOSPATIAL_HTTP_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        results = response.json()
    except (httpx.HTTPError, ValueError) as error:
        raise RuntimeError("geocoder_unavailable") from error
    if not isinstance(results, list):
        raise RuntimeError("geocoder_unavailable")

    candidates: list[GeocodeCandidate] = []
    for result in results:
        if not isinstance(result, dict):
            continue
        try:
            latitude = float(result["lat"])
            longitude = float(result["lon"])
            validate_coordinates(latitude, longitude)
        except (KeyError, TypeError, ValueError):
            continue
        provider_ref = None
        if result.get("osm_type") and result.get("osm_id"):
            provider_ref = f"{result['osm_type']}/{result['osm_id']}"
        candidates.append(
            GeocodeCandidate(
                label=str(result.get("display_name", ""))[:500],
                category=result.get("type") or result.get("class"),
                latitude=latitude,
                longitude=longitude,
                provider_ref=provider_ref,
            )
        )
    return candidates
