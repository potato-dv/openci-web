from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from app.utils.names import normalize_user_name


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
    model_config = ConfigDict(extra="forbid")

    first_name: str = Field(min_length=1, max_length=255)
    middle_name: str | None = Field(default=None, max_length=255)
    last_name: str = Field(min_length=1, max_length=255)
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

    @field_validator("first_name", "last_name", mode="before")
    @classmethod
    def normalize_required_name(cls, value):
        return normalize_user_name(value) if isinstance(value, str) else value

    @field_validator("middle_name", mode="before")
    @classmethod
    def trim_optional_name(cls, value):
        if isinstance(value, str):
            return normalize_user_name(value) or None
        return value

    @field_validator("house_number", "street", mode="before")
    @classmethod
    def normalize_required_address_text(cls, value):
        return normalize_user_name(value) if isinstance(value, str) else value

    @field_validator("unit_floor_building_name", "subdivision_village_purok", mode="before")
    @classmethod
    def normalize_optional_address_text(cls, value):
        if isinstance(value, str):
            return normalize_user_name(value) or None
        return value

    @model_validator(mode="after")
    def validate_full_name_length(self):
        full_name = " ".join(part for part in (self.first_name, self.middle_name, self.last_name) if part)
        if len(full_name) > 255:
            raise ValueError("Combined name must be 255 characters or fewer")
        return self

    @model_validator(mode="after")
    def validate_geography(self):
        from app.services.locations import validate_address

        validate_address(self)
        return self


class InvestigationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    reference_number: str
    first_name: str | None
    middle_name: str | None
    last_name: str | None
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

    @field_validator("first_name", "middle_name", "last_name", "subject_name", mode="before")
    @classmethod
    def format_existing_subject_name(cls, value):
        return normalize_user_name(value) if isinstance(value, str) else value

    @field_validator("house_number", "street", "unit_floor_building_name", "subdivision_village_purok", mode="before")
    @classmethod
    def format_existing_address_text(cls, value):
        return normalize_user_name(value) if isinstance(value, str) else value

class InvestigationUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    first_name: str | None = Field(default=None, min_length=1, max_length=255)
    middle_name: str | None = Field(default=None, max_length=255)
    last_name: str | None = Field(default=None, min_length=1, max_length=255)
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

    @field_validator("first_name", "last_name", mode="before")
    @classmethod
    def normalize_required_name(cls, value):
        return normalize_user_name(value) if isinstance(value, str) else value

    @field_validator("middle_name", mode="before")
    @classmethod
    def trim_optional_name(cls, value):
        if isinstance(value, str):
            return normalize_user_name(value) or None
        return value

    @field_validator("house_number", "street", mode="before")
    @classmethod
    def normalize_required_address_text(cls, value):
        return normalize_user_name(value) if isinstance(value, str) else value

    @field_validator("unit_floor_building_name", "subdivision_village_purok", mode="before")
    @classmethod
    def normalize_optional_address_text(cls, value):
        if isinstance(value, str):
            return normalize_user_name(value) or None
        return value

    @model_validator(mode="after")
    def validate_name_update(self):
        name_fields = {"first_name", "middle_name", "last_name"}
        supplied = name_fields.intersection(self.model_fields_set)
        if supplied and supplied != name_fields:
            raise ValueError("First, middle, and last name fields must be updated together")
        if supplied:
            if self.first_name is None or self.last_name is None:
                raise ValueError("First name and last name are required")
            full_name = " ".join(part for part in (self.first_name, self.middle_name, self.last_name) if part)
            if len(full_name) > 255:
                raise ValueError("Combined name must be 255 characters or fewer")
        return self

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
