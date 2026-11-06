from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


NoContactReason = Literal[
    "no_contact_person",
    "nobody_at_location",
    "requested_later_visit",
    "other",
]


class RouteActionInput(BaseModel):
    work_date: date
    route_revision: int = Field(gt=0)


class UnableToProceedInput(RouteActionInput):
    reason: NoContactReason
    notes: str | None = Field(default=None, max_length=4000)
    contact_available_from: datetime | None = None
    contact_available_until: datetime | None = None

    @model_validator(mode="after")
    def validate_attempt(self):
        if self.reason == "other" and not (self.notes or "").strip():
            raise ValueError("A note is required when the reason is Other")
        for name in ("contact_available_from", "contact_available_until"):
            value = getattr(self, name)
            if value is not None and value.tzinfo is None:
                raise ValueError("Contact availability timestamps must include a timezone")
        if (
            self.contact_available_from
            and self.contact_available_until
            and self.contact_available_until <= self.contact_available_from
        ):
            raise ValueError("Contact availability end must be after its start")
        return self


class NoContactFinalizeInput(RouteActionInput):
    event_id: int = Field(gt=0)


class RouteActionResponse(BaseModel):
    investigation_id: int
    route_revision: int
    started: bool


class NoContactEventSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    event_id: int
    reason: str
    notes: str | None
    state: Literal["deferred", "retrying", "retry_failed"]
    retry_number: int
    attempted_at: datetime
    work_date: date


class NoContactReviewItemResponse(BaseModel):
    event_id: int
    investigation_id: int
    reference_number: str
    subject_name: str
    assigned_agent_name: str | None
    priority: str
    reason: str
    state: Literal["deferred", "retrying", "retry_failed", "carried_over"]
    retry_number: int
    attempted_at: datetime
    work_date: date
    next_work_date: date | None
    notes: str | None


class NoContactReviewQueueResponse(BaseModel):
    items: list[NoContactReviewItemResponse]
    total: int
    page: int
    page_size: int


class RouteEventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    investigation_id: int
    reference_number: str | None = None
    address_display: str | None = None
    priority: str | None = None
    agent_id: int
    work_date: date
    planning_run_id: int | None
    parent_event_id: int | None
    event_type: Literal["no_contact", "shift_end_not_visited"]
    state: Literal["deferred", "retrying", "retry_failed", "carried_over", "resolved"]
    retry_number: int
    reason: str
    notes: str | None
    contact_available_from: datetime | None
    contact_available_until: datetime | None
    attempted_at: datetime
    next_work_date: date | None
    finalized_at: datetime | None
    can_finalize_no_contact: bool = False
    retry_actionable: bool = False
