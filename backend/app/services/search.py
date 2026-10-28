"""SQL expressions for searching structured names and Philippine addresses."""
from sqlalchemy import case, func, or_
from app.models.investigation import Investigation
from app.services.locations import catalog


def subject_expression():
    middle = func.trim(func.coalesce(Investigation.middle_name, ""))
    structured = (
        func.coalesce(Investigation.first_name, "") + " "
        + case((middle != "", middle + " "), else_="")
        + func.coalesce(Investigation.last_name, "")
    )
    return func.coalesce(Investigation.legacy_subject_name, structured)


def investigation_search(query: str):
    term = "%" + query.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
    address = func.coalesce(Investigation.legacy_address, "")
    for name in ("house_number", "unit_floor_building_name", "street", "subdivision_village_purok", "postal_code"):
        address = address + " " + func.coalesce(getattr(Investigation, name), "")
    codes = [code for code, name in catalog()["names"].items() if query.strip().casefold() in name.casefold()]
    return or_(Investigation.reference_number.ilike(term, escape="\\"), subject_expression().ilike(term, escape="\\"), address.ilike(term, escape="\\"),
        Investigation.region_code.in_(codes), Investigation.province_code.in_(codes), Investigation.city_municipality_code.in_(codes), Investigation.barangay_code.in_(codes))
