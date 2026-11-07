from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.user import User
from app.models.user_permission_override import UserPermissionOverride


AGENT_FEATURES: tuple[dict, ...] = (
    {
        "code": "investigation.request_revisit",
        "name": "Request a revisit",
        "description": "Ask for a correction visit to be added to a future route.",
        "default_allowed": True,
    },
    {
        "code": "route.view_own_history",
        "name": "View own route history",
        "description": "Open published routes from earlier work dates.",
        "default_allowed": True,
    },
    {
        "code": "investigation.view_own_history",
        "name": "View own history",
        "description": "View completed investigations, earlier report versions, and investigation activity for cases currently assigned to you.",
        "default_allowed": False,
    },
)

FEATURES_BY_CODE = {item["code"]: item for item in AGENT_FEATURES}

MANDATORY_AGENT_WORKFLOWS: tuple[dict, ...] = (
    {"name": "Visit reporting", "description": "Required report fields and submission checks."},
    {"name": "Route safety", "description": "Published stop sequence, shift, and route validation."},
    {"name": "Investigation ownership", "description": "Agents can access only currently assigned investigations."},
)


def effective_agent_permissions(db: Session, agent: User) -> dict[str, bool]:
    rows = db.query(UserPermissionOverride).filter(
        UserPermissionOverride.user_id == agent.id,
    ).all()
    overrides = {row.feature_code: row.effect for row in rows}
    return {
        item["code"]: (
            overrides[item["code"]] == "allow"
            if item["code"] in overrides
            else item["default_allowed"]
        )
        for item in AGENT_FEATURES
    }


def is_agent_feature_allowed(db: Session, agent: User, feature_code: str) -> bool:
    feature = FEATURES_BY_CODE.get(feature_code)
    if feature is None:
        raise ValueError(f"Unknown Agent feature: {feature_code}")
    override = db.query(UserPermissionOverride.effect).filter(
        UserPermissionOverride.user_id == agent.id,
        UserPermissionOverride.feature_code == feature_code,
    ).scalar()
    return override == "allow" if override is not None else feature["default_allowed"]


def require_agent_feature(db: Session, agent: User, feature_code: str) -> None:
    if agent.role != "agent" or not agent.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="This Agent feature is unavailable")
    if not is_agent_feature_allowed(db, agent, feature_code):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="This feature is disabled for your account")


def permission_state(db: Session, agent: User) -> dict:
    rows = db.query(UserPermissionOverride).filter(
        UserPermissionOverride.user_id == agent.id,
    ).all()
    overrides = {row.feature_code: row.effect for row in rows}
    return {
        "agent": {"id": agent.id, "name": agent.name, "is_active": agent.is_active},
        "features": [
            {
                **item,
                "override": overrides.get(item["code"]),
                "effective_allowed": (
                    overrides[item["code"]] == "allow"
                    if item["code"] in overrides
                    else item["default_allowed"]
                ),
            }
            for item in AGENT_FEATURES
        ],
        "mandatory_workflows": list(MANDATORY_AGENT_WORKFLOWS),
    }
