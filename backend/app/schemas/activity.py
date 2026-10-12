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
    actor_name: str | None = None
