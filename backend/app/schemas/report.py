from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ReportUpsert(BaseModel):
    content: str = Field(min_length=1, max_length=20_000)


class ReportResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    investigation_id: int
    author_id: int
    content: str
    status: Literal["draft", "submitted"]
    created_at: datetime
    updated_at: datetime
    submitted_at: datetime | None