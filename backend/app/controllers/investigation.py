from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from app.schemas.investigation import InvestigationCreate, InvestigationUpdate
from app.services.investigation import ( 
    assign_investigation,
    can_access_investigation,
    create_investigation,
    delete_investigation,
    permanently_delete_investigation,
    get_investigations,
    get_investigation,
    get_assignment_history,
    get_trashed_investigation,
    get_trashed_investigations,
    get_report,
    get_review_history,
    get_report_versions,
    review_investigation_report,
    restore_investigation,
    save_report_draft,
    submit_report,
    update_investigation,
    )

from fastapi import HTTPException, status
from app.models.user import User
from app.schemas.assignment import AssignmentCreate
from app.schemas.report import ReportUpsert
from app.schemas.review import ReviewCreate


def read_revisit_request(db: Session, investigation_id: int, current_user: User):
    investigation = get_one(db, investigation_id, current_user)
    if current_user.role == "agent" and investigation.assigned_agent_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only the assigned agent can view this revisit request")
    if investigation.assigned_agent_id is None:
        return None
    from app.services.agent_revisits import get_agent_revisit_request

    return get_agent_revisit_request(db, investigation.id, investigation.assigned_agent_id)


def create_revisit_request(db: Session, investigation_id: int, current_user: User):
    investigation = get_one(db, investigation_id, current_user)
    if current_user.role != "agent" or investigation.assigned_agent_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only the assigned agent can request a revisit")
    from app.services.agent_revisits import request_agent_revisit

    try:
        request = request_agent_revisit(db, investigation, current_user)
        from app.services.activity import record_activity

        record_activity(
            db,
            current_user,
            "investigation.revisit_requested",
            "investigation",
            investigation.id,
            {"target_work_date": str(request.target_work_date) if request.target_work_date else None},
        )
        db.commit()
        db.refresh(request)
        return request
    except ValueError as error:
        db.rollback()
        messages = {
            "investigation_not_found": (404, "Investigation not found"),
            "agent_assignment_changed": (409, "This investigation is no longer assigned to you"),
            "confirmed_location_required": (409, "The investigation needs a confirmed location before it can be routed"),
            "returned_report_required": (409, "Only a returned report can be routed for correction"),
        }
        code, message = messages.get(str(error), (409, "Could not request a revisit"))
        raise HTTPException(status_code=code, detail=message) from error

def create(db: Session, data: InvestigationCreate, current_user: User):
    try:
        investigation = create_investigation(db, data)
    except IntegrityError as error:
        db.rollback()
        raise HTTPException(status_code=409, detail="Could not create investigation; please retry") from error
    from app.services.activity import record_activity

    record_activity(db, current_user, "investigation.created", "investigation", investigation.id)
    return investigation

def get_all(db: Session, current_user: User):
    return get_investigations(db, current_user)


def get_trash(db: Session):
    return get_trashed_investigations(db)


def restore(
    db: Session,
    investigation_id: int,
    current_user: User,
):
    if current_user.role not in {"admin", "supervisor"}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You do not have permission to restore investigations")

    investigation = get_trashed_investigation(db, investigation_id)
    if investigation is None:
        raise HTTPException(status_code=404, detail="Investigation not found in Trash")

    return restore_investigation(db, investigation, current_user)


def assign(
    db: Session,
    investigation_id: int,
    data: AssignmentCreate,
    current_user: User,
):
    investigation = get_one(db, investigation_id, current_user)

    agent = db.query(User).filter(User.id == data.agent_id).first()

    if agent is None:
        raise HTTPException(status_code=404, detail="Agent not found")

    if agent.role != "agent":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Investigation can only be assigned to an agent",
        )

    try:
        previous_agent_id = investigation.assigned_agent_id
        assignment = assign_investigation(
            db,
            investigation,
            agent,
            current_user,
            data.note,
        )
        from app.services.activity import record_activity

        record_activity(db, current_user, "investigation.assigned", "investigation", investigation.id, {"agent_id": agent.id, "assignment_source": "manual"})
        # Route refresh is deliberately initiated only by the direct assignment
        # endpoint. Planning-run application also updates assignments and must
        # not recursively start another optimization.
        should_refresh_route = previous_agent_id != agent.id
        if not should_refresh_route and assignment.auto_route_status not in {"queued", "running"}:
            from datetime import datetime
            from zoneinfo import ZoneInfo

            from app.services.planning import planning_route_overview

            work_date = datetime.now(ZoneInfo("Asia/Manila")).date()
            overview = planning_route_overview(db, work_date, investigation.region_code)
            current_agent_route = next(
                (item for item in overview["agents"] if item["id"] == agent.id),
                None,
            )
            has_current_route = bool(
                current_agent_route
                and current_agent_route["route"]
                and current_agent_route["route"]["geometry_status"] == "ready"
                and any(
                    stop["investigation_id"] == investigation.id
                    for stop in current_agent_route["stops"]
                )
            )
            should_refresh_route = not has_current_route

        if should_refresh_route:
            from app.services.planning import queue_assignment_route_refresh

            refreshed = queue_assignment_route_refresh(
                db,
                assignment.id,
                [item for item in (previous_agent_id, agent.id) if item is not None],
                current_user,
            )
            if refreshed is not None:
                assignment = refreshed
        return assignment
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(error),
        ) from error
    except IntegrityError as error:
        db.rollback()
        raise HTTPException(status_code=409, detail="The investigation was assigned concurrently; refresh and try again") from error


def get_assignments(
    db: Session,
    investigation_id: int,
):
    return get_assignment_history(db, investigation_id)


def get_investigation_report(
    db: Session,
    investigation_id: int,
    current_user: User,
):
    investigation = get_one(db, investigation_id, current_user)
    report = get_report(db, investigation.id)
    return report


def get_investigation_report_versions(
    db: Session,
    investigation_id: int,
    current_user: User,
):
    investigation = get_one(db, investigation_id, current_user)
    return get_report_versions(db, investigation.id)


def save_investigation_report(
    db: Session,
    investigation_id: int,
    data: ReportUpsert,

    current_user: User,
    route_revision: int | None = None,
    work_date: date | None = None,
):
    investigation = get_one(db, investigation_id, current_user)

    if current_user.role != "agent" or investigation.assigned_agent_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the assigned agent can edit this report",
        )

    try:
        report = save_report_draft(
            db, investigation, current_user, data,
            route_revision=route_revision,
            work_date=work_date,
        )
        from app.services.activity import record_activity

        record_activity(db, current_user, "report.saved", "investigation", investigation.id)
        return report
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(error),
        ) from error


def submit_investigation_report(
    db: Session,
    investigation_id: int,
    current_user: User,
    route_revision: int | None = None,
    work_date: date | None = None,
):
    investigation = get_one(db, investigation_id, current_user)

    if current_user.role != "agent" or investigation.assigned_agent_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the assigned agent can submit this report",
        )

    try:
        report = submit_report(
            db, investigation, actor=current_user,
            route_revision=route_revision,
            work_date=work_date,
        )
        from app.services.activity import record_activity

        record_activity(db, current_user, "report.submitted", "investigation", investigation.id)
        try:
            # The durable trigger is saved with the report. Dispatch it now so
            # the remaining route does not wait for Beat's next scheduled tick.
            from app.workers.tasks import dispatch_planning_triggers_task

            dispatch_planning_triggers_task.delay()
        except Exception:
            import logging

            logging.getLogger("app.planning").exception(
                "Could not dispatch route refresh after report submission"
            )
        return report
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(error),
        ) from error


def review_report(
    db: Session,
    investigation_id: int,
    data: ReviewCreate,
    current_user: User,
):
    investigation = get_one(db, investigation_id, current_user)
    comments = data.comments.strip() if data.comments else None

    try:
        review = review_investigation_report(
            db,
            investigation,
            current_user,
            data.decision,
            comments,
        )
        from app.services.activity import record_activity

        record_activity(db, current_user, "report.reviewed", "investigation", investigation.id, {"decision": data.decision})
        return review
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(error),
        ) from error


def get_reviews(
    db: Session,
    investigation_id: int,
    current_user: User,
):
    get_one(db, investigation_id, current_user)
    return get_review_history(db, investigation_id)

def get_one(
    db: Session,
    investigation_id: int,
    current_user: User,
):
    investigation = get_investigation(db, investigation_id)

    if investigation is None:
        raise HTTPException(
            status_code=404,
            detail="Investigation not found",
        )

    if not can_access_investigation(investigation, current_user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have access to this investigation",
        )

    return investigation

def update(
    db: Session,
    investigation_id: int,
    data: InvestigationUpdate,
    current_user: User,
):
    investigation = get_investigation(db, investigation_id)

    if investigation is None:
        raise HTTPException(
            status_code=404,
            detail="Investigation not found",
        )

    if not can_access_investigation(investigation, current_user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have access to this investigation",
        )

    if current_user.role == "agent":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Agents cannot edit investigation details",
        )

    try:
        updated = update_investigation(db, investigation, data)
    except ValueError as error:
        db.rollback()
        raise HTTPException(status_code=422, detail=str(error)) from error
    from app.services.activity import record_activity

    record_activity(db, current_user, "investigation.updated", "investigation", investigation.id, {"fields": list(data.model_dump(exclude_unset=True))})
    planning_fields = {
        "legacy_address", "house_number", "unit_floor_building_name", "street",
        "subdivision_village_purok", "region_code", "province_code",
        "city_municipality_code", "barangay_code", "postal_code", "priority",
        "service_duration_seconds", "visit_not_before_at", "visit_due_at",
    }
    if planning_fields.intersection(data.model_dump(exclude_unset=True)) and updated.location_confirmed and updated.region_code:
        from app.services.planning import queue_automatic_planning

        try:
            queue_automatic_planning(db, updated.region_code, current_user)
        except Exception:
            import logging

            logging.getLogger("app.planning").exception(
                "Could not queue automatic planning after investigation update"
            )
    return updated

def delete(
    db: Session,
    investigation_id: int,
    current_user: User,
):
    investigation = get_investigation(db, investigation_id)

    if investigation is None:
        raise HTTPException(
            status_code=404,
            detail="Investigation not found",
        )

    if current_user.role not in {"admin", "supervisor"}:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only admins and supervisors can move investigations to Trash",
        )

    delete_investigation(db, investigation, current_user)
    return {"message": "Investigation moved to Trash"}


def permanently_delete(
    db: Session,
    investigation_id: int,
    current_user: User,
):
    if current_user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only admins can permanently delete investigations")

    investigation = get_trashed_investigation(db, investigation_id)
    if investigation is None:
        raise HTTPException(status_code=404, detail="Investigation not found in Trash")

    permanently_delete_investigation(db, investigation, current_user)
