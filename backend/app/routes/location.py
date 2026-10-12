from fastapi import APIRouter, Depends, Query

from app.models.user import User
from app.services.locations import get_barangays, get_cities, get_provinces, get_regions
from app.utils.auth import get_current_user

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
