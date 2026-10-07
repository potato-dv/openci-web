from pydantic import BaseModel


class InvestigationCreate(BaseModel):
    reference_number: str
    subject_name: str
    address: str
    status: str = "pending"
    priority: str = "normal"

class InvestigationUpdate(BaseModel):
    subject_name: str | None = None
    address: str | None = None
    status: str | None = None
    priority: str | None = None