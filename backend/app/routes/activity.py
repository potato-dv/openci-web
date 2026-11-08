from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import String, cast, func, or_
from sqlalchemy.orm import Session, joinedload

from app.database.session import get_db
from app.models.activity import ActivityLog
from app.models.investigation import Investigation
from app.models.user import User
from app.schemas.activity import (
    ActivityLogActorOption,
    ActivityLogFilterOptions,
    ActivityLogPageResponse,
    ActivityLogQueryItem,
    ActivityLogResponse,
)
from app.services.activity_presentation import (
    detail_fields,
    record_label,
    related_user_ids,
    summarize_activity,
)
from app.utils.auth import require_roles

router = APIRouter(prefix="/activity-logs", tags=["Activity"])


SORT_COLUMNS = {
    "created_at": ActivityLog.created_at,
    "action": ActivityLog.action,
    "actor": User.name,
    "object_type": ActivityLog.object_type,
    "object_id": ActivityLog.object_id,
}


def _private_no_store(response: Response) -> None:
    response.headers["Cache-Control"] = "private, no-store"


def _aware_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        raise HTTPException(
            status_code=422,
            detail="Activity log date filters must include a timezone offset.",
        )
    return value.astimezone(timezone.utc)


@router.get(
    "/filter-options",
    response_model=ActivityLogFilterOptions,
)
def activity_log_filter_options(
    response: Response,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles("admin")),
):
    _private_no_store(response)
    actions = [
        value
        for (value,) in db.query(ActivityLog.action)
        .distinct()
        .order_by(ActivityLog.action.asc())
        .all()
    ]
    object_types = [
        value
        for (value,) in db.query(ActivityLog.object_type)
        .distinct()
        .order_by(ActivityLog.object_type.asc())
        .all()
    ]
    actors = [
        ActivityLogActorOption(id=user.id, name=user.name)
        for user in db.query(User).order_by(User.name.asc()).all()
    ]
    if db.query(ActivityLog.id).filter(ActivityLog.actor_id.is_(None)).first():
        actors.insert(0, ActivityLogActorOption(id=None, name="System or deleted account"))
    return ActivityLogFilterOptions(
        actions=actions,
        object_types=object_types,
        actors=actors,
    )


@router.get(
    "/query",
    response_model=ActivityLogPageResponse,
)
def query_activity_logs(
    response: Response,
    q: str = Query(default="", max_length=200),
    action: str | None = Query(default=None, max_length=80),
    actor_id: int | None = Query(default=None, ge=1),
    actor_type: Literal["system"] | None = Query(default=None),
    object_type: str | None = Query(default=None, max_length=80),
    object_id: int | None = Query(default=None, ge=1),
    created_from: datetime | None = Query(default=None),
    created_to: datetime | None = Query(default=None),
    sort: Literal["created_at", "action", "actor", "object_type", "object_id"] = "created_at",
    direction: Literal["asc", "desc"] = "desc",
    page: int = Query(default=1, ge=1),
    page_size: Literal[25, 50, 100] = 25,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles("admin")),
):
    _private_no_store(response)
    if actor_id is not None and actor_type is not None:
        raise HTTPException(
            status_code=422,
            detail="Choose either an actor or the system actor filter, not both.",
        )

    created_from = _aware_utc(created_from)
    created_to = _aware_utc(created_to)
    if created_from is not None and created_to is not None and created_to <= created_from:
        raise HTTPException(
            status_code=422,
            detail="The activity log end date must be after the start date.",
        )

    query = db.query(ActivityLog).outerjoin(User, ActivityLog.actor_id == User.id)
    search = q.strip().lower()
    if search:
        details_text = func.lower(cast(ActivityLog.details, String))
        search_value = f"%{search}%"
        query = query.filter(
            or_(
                func.lower(User.name).like(search_value),
                func.lower(ActivityLog.action).like(search_value),
                func.lower(ActivityLog.object_type).like(search_value),
                cast(ActivityLog.object_id, String).like(search_value),
                details_text.like(search_value),
            )
        )
    if action:
        query = query.filter(ActivityLog.action == action.strip())
    if actor_id is not None:
        query = query.filter(ActivityLog.actor_id == actor_id)
    if actor_type == "system":
        query = query.filter(ActivityLog.actor_id.is_(None))
    if object_type:
        query = query.filter(ActivityLog.object_type == object_type.strip())
    if object_id is not None:
        query = query.filter(ActivityLog.object_id == object_id)
    if created_from is not None:
        query = query.filter(ActivityLog.created_at >= created_from)
    if created_to is not None:
        query = query.filter(ActivityLog.created_at < created_to)

    total = query.order_by(None).count()
    sort_column = SORT_COLUMNS[sort]
    primary_order = sort_column.desc() if direction == "desc" else sort_column.asc()
    tie_order = ActivityLog.id.desc() if direction == "desc" else ActivityLog.id.asc()
    rows = (
        query.options(joinedload(ActivityLog.actor))
        .order_by(primary_order, tie_order)
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    related_ids = set()
    investigation_ids = set()
    user_record_ids = set()
    for row in rows:
        if row.object_id is not None and row.object_type == "investigation":
            investigation_ids.add(row.object_id)
        if row.object_id is not None and row.object_type == "user":
            user_record_ids.add(row.object_id)
        if isinstance(row.details, dict):
            related_ids.update(related_user_ids(row.details))
            if row.object_type == "agent_shift" and isinstance(row.details.get("agent_id"), int):
                related_ids.add(row.details["agent_id"])
    related_ids.update(user_record_ids)
    related_users = {
        user.id: user.name
        for user in db.query(User.id, User.name).filter(User.id.in_(related_ids)).all()
    } if related_ids else {}
    investigations = {
        investigation.id: investigation
        for investigation in db.query(Investigation)
        .filter(Investigation.id.in_(investigation_ids))
        .all()
    } if investigation_ids else {}
    resolved_records: dict[tuple[str, int], str] = {}
    for row in rows:
        if row.object_id is None:
            continue
        if row.object_type == "user":
            name = related_users.get(row.object_id)
            resolved_records[(row.object_type, row.object_id)] = (
                f"{name} (User ID: {row.object_id})"
                if name
                else f"User ID: {row.object_id} (account no longer exists)"
            )
        elif row.object_type == "investigation":
            investigation = investigations.get(row.object_id)
            resolved_records[(row.object_type, row.object_id)] = (
                f"{investigation.reference_number} · {investigation.subject_name} "
                f"(Investigation ID: {row.object_id})"
                if investigation
                else f"Investigation ID: {row.object_id} (record no longer exists)"
            )
        elif row.object_type == "agent_shift":
            agent_id = row.details.get("agent_id") if isinstance(row.details, dict) else None
            agent_name = related_users.get(agent_id) if isinstance(agent_id, int) else None
            resolved_records[(row.object_type, row.object_id)] = (
                f"{agent_name} · Agent shift ID: {row.object_id}"
                if agent_name
                else f"Agent shift ID: {row.object_id}"
            )

    items = [
        ActivityLogQueryItem(
            id=row.id,
            actor_id=row.actor_id,
            actor_name=row.actor_name,
            action=row.action,
            object_type=row.object_type,
            object_id=row.object_id,
            record_label=record_label(row.object_type, row.object_id, resolved_records),
            summary=summarize_activity(row.action, row.details, related_users),
            detail_fields=detail_fields(row.details if isinstance(row.details, dict) else {}, related_users),
            created_at=row.created_at,
        )
        for row in rows
    ]
    return ActivityLogPageResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/", response_model=list[ActivityLogResponse])
def list_activity_logs(
    response: Response,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles("admin")),
):
    """Legacy compatibility endpoint; the UI uses /activity-logs/query."""
    _private_no_store(response)
    return (
        db.query(ActivityLog)
        .options(joinedload(ActivityLog.actor))
        .order_by(ActivityLog.created_at.desc())
        .limit(250)
        .all()
    )
