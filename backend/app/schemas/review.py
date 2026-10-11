from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ReviewCreate(BaseModel):
    decision: Literal["approved", "returned_for_correction"]
    comments: str | None = Field(default=None, max_length=5_000)


class ReviewResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    investigation_id: int
    report_id: int
    reviewer_id: int
    decision: Literal["approved", "returned_for_correction"]
    comments: str | None
    reviewed_at: datetime