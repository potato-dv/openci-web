from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


InvestigationStatus = Literal[
    "pending",
    "assigned",
    "in_progress",
    "under_review",
    "returned_for_correction",
    "completed",
]
InvestigationPriority = Literal["normal", "high", "urgent"]


class InvestigationCreate(BaseModel):
    subject_name: str = Field(min_length=1, max_length=255)
    house_number: str = Field(min_length=1, max_length=100)
    unit_floor_building_name: str | None = Field(default=None, max_length=150)
    street: str = Field(min_length=1, max_length=200)
    subdivision_village_purok: str | None = Field(default=None, max_length=200)
    region_code: str = Field(min_length=10, max_length=10)
    province_code: str | None = Field(default=None, min_length=10, max_length=10)
    city_municipality_code: str = Field(min_length=10, max_length=10)
    barangay_code: str = Field(min_length=10, max_length=10)
    postal_code: str | None = Field(default=None, pattern=r"^\d{4}$")
    priority: InvestigationPriority = "normal"

    @model_validator(mode="after")
    def validate_geography(self):
        from app.services.locations import validate_address

        validate_address(self)
        return self


class InvestigationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    reference_number: str
    subject_name: str
    legacy_address: str | None
    address_display: str
    house_number: str | None
    unit_floor_building_name: str | None
    street: str | None
    subdivision_village_purok: str | None
    region_code: str | None
    province_code: str | None
    city_municipality_code: str | None
    barangay_code: str | None
    postal_code: str | None
    status: InvestigationStatus
    priority: InvestigationPriority
    assigned_agent_id: int | None
    created_at: datetime
    assigned_agent_name: str | None = None

class InvestigationUpdate(BaseModel):
    subject_name: str | None = Field(default=None, min_length=1, max_length=255)
    house_number: str | None = Field(default=None, min_length=1, max_length=100)
    unit_floor_building_name: str | None = Field(default=None, max_length=150)
    street: str | None = Field(default=None, min_length=1, max_length=200)
    subdivision_village_purok: str | None = Field(default=None, max_length=200)
    region_code: str | None = Field(default=None, min_length=10, max_length=10)
    province_code: str | None = Field(default=None, min_length=10, max_length=10)
    city_municipality_code: str | None = Field(default=None, min_length=10, max_length=10)
    barangay_code: str | None = Field(default=None, min_length=10, max_length=10)
    postal_code: str | None = Field(default=None, pattern=r"^\d{4}$")
    priority: InvestigationPriority | None = None

    @model_validator(mode="after")
    def validate_geography(self):
        for name in ("house_number", "street"):
            if name in self.model_fields_set and not getattr(self, name):
                raise ValueError(f"{name.replace('_', ' ').capitalize()} is required")
        geography = {"region_code", "province_code", "city_municipality_code", "barangay_code"}
        if geography.intersection(self.model_fields_set):
            if not geography.issubset(self.model_fields_set) or not self.region_code or not self.city_municipality_code or not self.barangay_code:
                raise ValueError("Address geography must be updated as a complete region, province, city, and barangay selection")
            if not self.house_number or not self.street:
                raise ValueError("House/building number and street are required when changing address locations")
            from app.services.locations import validate_address

            validate_address(self)
        return self
