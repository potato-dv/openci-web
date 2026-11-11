from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from app.dependencies.rate_limit import general_api_rate_limit
from app.database.session import get_db
from app.models.user import User
from app.services.agent_permissions import AGENT_FEATURES, MANDATORY_AGENT_WORKFLOWS
from app.utils.auth import require_roles


router = APIRouter(prefix="/agent-permissions", tags=["Agent Permissions"], dependencies=[Depends(general_api_rate_limit)])


@router.get("/catalog")
def get_agent_permission_catalog(
    response: Response,
    _: User = Depends(require_roles("admin")),
):
    response.headers["Cache-Control"] = "private, no-store"
    return {
        "features": list(AGENT_FEATURES),
        "mandatory_workflows": list(MANDATORY_AGENT_WORKFLOWS),
    }
