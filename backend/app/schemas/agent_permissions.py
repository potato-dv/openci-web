from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, field_validator

from app.services.agent_permissions import FEATURES_BY_CODE


PermissionEffect = Literal["allow", "deny", "inherit"]


class AgentPermissionOverrideMap(BaseModel):
    overrides: dict[str, PermissionEffect]

    @field_validator("overrides")
    @classmethod
    def validate_complete_override_map(cls, value: dict[str, str]) -> dict[str, str]:
        unknown = set(value) - set(FEATURES_BY_CODE)
        missing = set(FEATURES_BY_CODE) - set(value)
        if unknown:
            raise ValueError(f"Unknown Agent feature codes: {', '.join(sorted(unknown))}")
        if missing:
            raise ValueError(f"Complete override map is missing: {', '.join(sorted(missing))}")
        if value.get("investigation.view_own_history") == "inherit":
            raise ValueError("View own history must be explicitly allowed or denied")
        return value


class AgentPermissionFeature(BaseModel):
    code: str
    name: str
    description: str
    default_allowed: bool
    override: Literal["allow", "deny"] | None = None
    effective_allowed: bool


class AgentPermissionState(BaseModel):
    agent: dict
    features: list[AgentPermissionFeature]
    mandatory_workflows: list[dict]


class AgentPermissionHistoryItem(BaseModel):
    id: int
    actor_name: str | None
    created_at: datetime
    old_overrides: dict[str, str]
    new_overrides: dict[str, str]
    old_effective: dict[str, bool]
    new_effective: dict[str, bool]


class AgentPermissionHistoryResponse(BaseModel):
    items: list[AgentPermissionHistoryItem]
    total: int
    limit: int
    offset: int


class InvestigationActivityItem(BaseModel):
    id: int
    label: str
    actor_name: str | None
    created_at: datetime


class InvestigationActivityResponse(BaseModel):
    items: list[InvestigationActivityItem]


class RevisitRequestState(BaseModel):
    request: "RevisitRequestResponse | None"
    can_request: bool


from app.schemas.report import RevisitRequestResponse

RevisitRequestState.model_rebuild()
