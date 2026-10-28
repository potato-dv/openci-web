from fastapi import APIRouter, Depends, Query

from app.models.user import User
from app.services.locations import get_barangays, get_cities, get_provinces, get_regions
from app.utils.auth import get_current_user, require_roles
from app.utils.features import require_planning_enabled
from app.services.geocoding import search_locations
from app.schemas.planning import GeocodeCandidate
from fastapi import HTTPException

router = APIRouter(prefix="/locations", tags=["Locations"])


@router.get("/regions")
def regions(_: User = Depends(get_current_user)):
    return get_regions()


@router.get("/regions/{region_code}/provinces")
def provinces(region_code: str, _: User = Depends(get_current_user)):
    return get_provinces(region_code)


@router.get("/regions/{region_code}/cities-municipalities")
def cities_municipalities(
    region_code: str,
    province_code: str | None = Query(default=None),
    _: User = Depends(get_current_user),
):
    return get_cities(region_code, province_code)


@router.get("/cities-municipalities/{city_code}/barangays")
def barangays(city_code: str, _: User = Depends(get_current_user)):
    return get_barangays(city_code)


@router.get("/geocode-suggestions", response_model=list[GeocodeCandidate], dependencies=[Depends(require_planning_enabled)])
def geocode_suggestions(q: str = Query(min_length=3, max_length=500), _: User = Depends(require_roles("admin", "supervisor"))):
    try:
        return search_locations(q.strip())
    except RuntimeError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
