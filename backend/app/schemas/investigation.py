from typing import Literal

from pydantic import BaseModel


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
    reference_number: str
    subject_name: str
    address: str
    status: Literal["pending"] = "pending"
    priority: InvestigationPriority = "normal"

class InvestigationUpdate(BaseModel):
    subject_name: str | None = None
    address: str | None = None
    status: InvestigationStatus | None = None
    priority: InvestigationPriority | None = None