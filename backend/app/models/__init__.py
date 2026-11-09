from app.models.activity import ActivityLog
from app.models.assignment import InvestigationAssignment
from app.models.investigation import Investigation
from app.models.report import InvestigationReport
from app.models.review import InvestigationReview
from app.models.user import User
from app.models.planning import AgentShift, PlanningItem, PlanningRun, PlanningRoute
from app.models.agent_schedule import AgentWorkProfile, AgentWeeklySchedule, PlanningTrigger
from app.models.agent_revisit import AgentRevisitRequest
from app.models.auth_session import AuthSession, AuthRefreshToken
from app.models.route_event import InvestigationRouteEvent
from app.models.user_permission_override import UserPermissionOverride
from app.models.realtime_outbox import RealtimeOutboxEvent

# Model imports register the transaction outbox hooks for API and Celery sessions.
from app.realtime.orm_events import register_orm_event_listeners

register_orm_event_listeners()

__all__ = ["ActivityLog", "InvestigationAssignment", "Investigation", "InvestigationReport", "InvestigationReview", "User", "AgentShift", "PlanningItem", "PlanningRun", "PlanningRoute", "AgentWorkProfile", "AgentWeeklySchedule", "PlanningTrigger", "AgentRevisitRequest", "AuthSession", "AuthRefreshToken", "InvestigationRouteEvent", "UserPermissionOverride", "RealtimeOutboxEvent"]
