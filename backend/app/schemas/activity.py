from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ActivityLogResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    actor_id: int | None
    actor_name: str | None
    action: str
    object_type: str
    object_id: int | None
    details: dict
    created_at: datetime


class ActivityLogDetail(BaseModel):
    key: str
    label: str
    value: str
    redacted: bool = False


class ActivityLogQueryItem(BaseModel):
    id: int
    actor_id: int | None
    actor_name: str | None
    action: str
    object_type: str
    object_id: int | None
    record_label: str
    summary: str
    detail_fields: list[ActivityLogDetail]
    created_at: datetime


class ActivityLogPageResponse(BaseModel):
    items: list[ActivityLogQueryItem]
    total: int
    page: int
    page_size: int


class ActivityLogActorOption(BaseModel):
    id: int | None
    name: str


class ActivityLogFilterOptions(BaseModel):
    actions: list[str]
    object_types: list[str]
    actors: list[ActivityLogActorOption]
