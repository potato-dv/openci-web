from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class AssignmentCreate(BaseModel):
    agent_id: int = Field(gt=0)
    note: str | None = Field(default=None, max_length=500)


class AssignmentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    investigation_id: int
    agent_id: int
    assigned_by_id: int
    agent_name: str
    assigned_by_name: str
    note: str | None
    is_active: bool
    assigned_at: datetime
    unassigned_at: datetime | None
