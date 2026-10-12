from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


VisitOutcome = Literal["visited", "no_access", "unable_to_locate"]
InvestigationOutcome = Literal["verified", "not_verified", "unable_to_verify", "inconclusive"]
OccupancyStatus = Literal["occupied", "vacant", "unknown", "not_applicable"]
ReportStatus = Literal["draft", "submitted", "approved", "returned_for_correction"]


class ReportUpsert(BaseModel):
    content: str = Field(min_length=1, max_length=20_000)
    visit_outcome: VisitOutcome | None = None
    outcome: InvestigationOutcome | None = None
    verified_address: str | None = Field(default=None, max_length=500)
    occupancy_status: OccupancyStatus | None = None
    property_condition: str | None = None
    interaction_notes: str | None = None
    visited_at: datetime | None = None


class ReportResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    investigation_id: int
    author_id: int
    author_name: str
    version: int
    content: str
    visit_outcome: VisitOutcome | None
    outcome: InvestigationOutcome | None
    verified_address: str | None
    occupancy_status: OccupancyStatus | None
    property_condition: str | None
    interaction_notes: str | None
    visited_at: datetime | None
    status: ReportStatus
    created_at: datetime
    updated_at: datetime
    submitted_at: datetime | None
