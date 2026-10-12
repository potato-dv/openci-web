"""Offline location lookups from the July 2026 PSGC snapshot."""

import json
from functools import lru_cache
from pathlib import Path

from fastapi import HTTPException

DATA_PATH = Path(__file__).resolve().parents[1] / "data" / "psgc-2026-07-13.json"
CITY_TYPES = {"municipality", "component_city", "highly_urbanized_city", "independent_component_city"}


@lru_cache(maxsize=1)
def catalog() -> dict:
    rows = json.loads(DATA_PATH.read_text(encoding="utf-8"))
    by_code = {row["psgc_id"]: row for row in rows}
    regions = [row for row in rows if row["type"] == "region"]
    provinces = [row for row in rows if row["type"] == "province"]
    cities = [row for row in rows if row["type"] in CITY_TYPES]
    barangays = [row for row in rows if row["type"] == "barangay"]

    def ancestor(row: dict, types: set[str]) -> dict | None:
        parent_code = row.get("parent_psgc_id")
        while parent_code and parent_code != "0000000000":
            parent = by_code.get(parent_code)
            if parent is None:
                return None
            if parent["type"] in types:
                return parent
            parent_code = parent.get("parent_psgc_id")
        return None

    def location(row: dict) -> dict:
        return {"code": row["psgc_id"], "name": row["name"]}

    province_parents = {row["psgc_id"]: row.get("parent_psgc_id") for row in provinces}
    region_codes = {row["psgc_id"] for row in regions}
    city_index: dict[str, dict] = {}
    for city in cities:
        province = ancestor(city, {"province"})
        region = ancestor(city, {"region"})
        city_index[city["psgc_id"]] = {
            **location(city),
            "region_code": region["psgc_id"] if region else None,
            "province_code": province["psgc_id"] if province else None,
            "type": city["type"],
        }

    barangay_index: dict[str, dict] = {}
    barangays_by_city: dict[str, list[dict]] = {}
    for barangay in barangays:
        city = ancestor(barangay, CITY_TYPES)
        if city is None:
            continue
        barangay_index[barangay["psgc_id"]] = {
            **location(barangay),
            "city_code": city["psgc_id"],
        }
        barangays_by_city.setdefault(city["psgc_id"], []).append(
            {"code": barangay["psgc_id"], "name": barangay["name"]}
        )

    return {
        "regions": [location(row) for row in sorted(regions, key=lambda item: item["name"])],
        "provinces": [
            {**location(row), "region_code": province_parents[row["psgc_id"]]}
            for row in sorted(provinces, key=lambda item: item["name"])
        ],
        "cities": list(city_index.values()),
        "barangays": barangay_index,
        "barangays_by_city": barangays_by_city,
        "names": {row["psgc_id"]: row["name"] for row in rows},
        "region_codes": region_codes,
    }


def get_regions() -> list[dict]:
    return catalog()["regions"]


def get_provinces(region_code: str) -> list[dict]:
    data = catalog()
    if region_code not in data["region_codes"]:
        raise HTTPException(status_code=404, detail="Region not found")
    return [item for item in data["provinces"] if item["region_code"] == region_code]


def get_cities(region_code: str, province_code: str | None) -> list[dict]:
    data = catalog()
    if region_code not in data["region_codes"]:
        raise HTTPException(status_code=404, detail="Region not found")
    if province_code is not None:
        province = next((p for p in data["provinces"] if p["code"] == province_code), None)
        if province is None or province["region_code"] != region_code:
            raise HTTPException(status_code=404, detail="Province does not belong to the selected region")
    return [
        {"code": item["code"], "name": item["name"], "type": item["type"]}
        for item in data["cities"]
        if item["region_code"] == region_code and item["province_code"] == province_code
    ]


def get_barangays(city_code: str) -> list[dict]:
    data = catalog()
    if not any(city["code"] == city_code for city in data["cities"]):
        raise HTTPException(status_code=404, detail="City or municipality not found")
    return data["barangays_by_city"].get(city_code, [])


def validate_address(data: object) -> None:
    values = data.model_dump()
    catalog_data = catalog()
    region = next((x for x in catalog_data["regions"] if x["code"] == values["region_code"]), None)
    province = next((x for x in catalog_data["provinces"] if x["code"] == values["province_code"]), None) if values["province_code"] else None
    city = next((x for x in catalog_data["cities"] if x["code"] == values["city_municipality_code"]), None)
    barangay = catalog_data["barangays"].get(values["barangay_code"])
    if region is None or city is None or barangay is None:
        raise ValueError("Select a valid region, city or municipality, and barangay")
    if city["region_code"] != region["code"]:
        raise ValueError("The selected city or municipality does not belong to the selected region")
    if city["province_code"]:
        if province is None or province["code"] != city["province_code"] or province["region_code"] != region["code"]:
            raise ValueError("Select the province that contains the selected city or municipality")
    elif province is not None:
        raise ValueError("This city or municipality does not have a province")
    if barangay["city_code"] != city["code"]:
        raise ValueError("The selected barangay does not belong to the selected city or municipality")


def address_display(investigation: object) -> str:
    data = catalog()
    values = data["names"]
    parts = [
        getattr(investigation, "house_number", None),
        getattr(investigation, "unit_floor_building_name", None),
        getattr(investigation, "street", None),
        getattr(investigation, "subdivision_village_purok", None),
        values.get(getattr(investigation, "barangay_code", None)),
        values.get(getattr(investigation, "city_municipality_code", None)),
        values.get(getattr(investigation, "province_code", None)),
        values.get(getattr(investigation, "region_code", None)),
        getattr(investigation, "postal_code", None),
    ]
    formatted = ", ".join(part for part in parts if part)
    return formatted or getattr(investigation, "legacy_address", None) or "—"
