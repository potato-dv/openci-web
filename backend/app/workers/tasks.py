from datetime import datetime, timezone

from app.workers.celery_app import celery_app
from app.config.settings import PLANNING_ENABLED
from app.database import SessionLocal
from app.models.assignment import InvestigationAssignment
from app.models.investigation import Investigation
from app.models.planning import AgentShift, PlanningItem, PlanningRun
from app.models.user import User
from app.services.investigation import is_valid_status_transition
from app.services.planning import (
    PlanningConflict,
    _geometry_complete,
    apply_run,
    execute_run,
    planning_route_overview,
    queue_automatic_planning,
    reconcile_missing_route_scopes,
    sync_assignment_route_refresh,
)
from app.services.agent_schedules import (
    MANILA,
    dispatch_planning_triggers,
    enqueue_planning_trigger,
    materialize_work_date,
)
from app.services.agent_revisits import activate_due_revisit_requests
from app.services.auth_sessions import prune_old_auth_sessions
from app.services.shift_expiry import process_shift_end_investigations


class RetryablePlanningFailure(RuntimeError):
    pass


@celery_app.task(
    bind=True,
    name="app.workers.tasks.prune_expired_auth_sessions",
    autoretry_for=(Exception,),
    retry_backoff=True,
    max_retries=2,
    soft_time_limit=60,
    time_limit=90,
)
def prune_expired_auth_sessions(_task):
    db = SessionLocal()
    try:
        return {"deleted_sessions": prune_old_auth_sessions(db)}
    finally:
        db.close()


@celery_app.task(
    bind=True,
    name="app.workers.tasks.expire_shift_investigations",
    autoretry_for=(Exception,),
    retry_backoff=True,
    max_retries=3,
    soft_time_limit=60,
    time_limit=90,
)
def expire_shift_investigations(_task):
    """Apply shift-end transitions independently of optimizer availability."""
    db = SessionLocal()
    try:
        return process_shift_end_investigations(db)
    finally:
        db.close()


def _sync_auto_route_assignments(db, run: PlanningRun) -> None:
    assignment_ids = list(run.auto_assignment_ids or [])
    if run.auto_assignment_id is not None:
        assignment_ids.append(run.auto_assignment_id)
    if run.investigation_ids:
        current_assignments = db.query(InvestigationAssignment.id).join(
            Investigation, Investigation.id == InvestigationAssignment.investigation_id,
        ).filter(
            InvestigationAssignment.is_active.is_(True),
            Investigation.id.in_(run.investigation_ids),
            Investigation.assigned_agent_id == InvestigationAssignment.agent_id,
        ).all()
        assignment_ids.extend(assignment_id for (assignment_id,) in current_assignments)
    assignment_ids = list(dict.fromkeys(assignment_ids))
    current_route_agents = None
    if run.status not in {"queued", "running", "ready"}:
        overview = planning_route_overview(db, run.work_date)
        current_route_agents = {agent["id"]: agent for agent in overview["agents"]}
    for assignment_id in assignment_ids:
        sync_assignment_route_refresh(
            db,
            assignment_id,
            planning_run_id=run.id,
            current_route_agents=current_route_agents,
        )


@celery_app.task(
    bind=True,
    name="app.workers.tasks.reconcile_missing_routes",
    autoretry_for=(Exception,),
    retry_backoff=True,
    max_retries=2,
    soft_time_limit=60,
    time_limit=90,
)
def reconcile_missing_routes(_task):
    if not PLANNING_ENABLED:
        return {"status": "disabled"}
    db = SessionLocal()
    try:
        today = datetime.now(MANILA).date()
        materialized = materialize_work_date(db, today)
        activated_revisits = activate_due_revisit_requests(db, today)
        if materialized:
            scopes = {
                region_code for (region_code,) in db.query(AgentShift.region_code).filter(
                    AgentShift.work_date == today,
                    AgentShift.is_available.is_(True),
                ).distinct().all()
            }
            for scope in scopes:
                enqueue_planning_trigger(db, today, scope, "daily_schedule_reconciliation")

        # Recover only confirmed unassigned cases that have never appeared in
        # a planning run. Prior permanent failures are retried only after an
        # explicit input event changes their trigger generation.
        runs = db.query(PlanningRun).filter(PlanningRun.work_date == today).all()
        attempted_case_ids = {case_id for run in runs for case_id in (run.investigation_ids or [])}
        new_cases = db.query(Investigation).filter(
            Investigation.deleted_at.is_(None),
            Investigation.status == "pending",
            Investigation.assigned_agent_id.is_(None),
            Investigation.location_confirmed_at.is_not(None),
            Investigation.latitude.is_not(None),
            Investigation.longitude.is_not(None),
        ).order_by(Investigation.id).all()
        fresh_regions = {case.region_code for case in new_cases if case.id not in attempted_case_ids and case.region_code}
        for scope in fresh_regions:
            has_agent = db.query(AgentShift.id).filter(
                AgentShift.work_date == today,
                AgentShift.is_available.is_(True),
                AgentShift.region_code.in_((scope, "ALL")),
            ).first() is not None
            if has_agent:
                enqueue_planning_trigger(db, today, scope, "pending_case_reconciliation")
        db.commit()
        dispatched = dispatch_planning_triggers(db)
        recovered = reconcile_missing_route_scopes(db, today)
        return {
            "materialized_shifts": materialized,
            "activated_revisits": activated_revisits,
            "trigger_dispatch": dispatched,
            "route_recovery": recovered,
        }
    finally:
        db.close()


@celery_app.task(
    bind=True,
    name="app.workers.tasks.dispatch_planning_triggers",
    autoretry_for=(Exception,),
    retry_backoff=True,
    max_retries=2,
    soft_time_limit=60,
    time_limit=90,
)
def dispatch_planning_triggers_task(_task):
    if not PLANNING_ENABLED:
        return {"status": "disabled"}
    db = SessionLocal()
    try:
        return dispatch_planning_triggers(db)
    finally:
        db.close()


@celery_app.task(
    bind=True,
    name="app.workers.tasks.materialize_recurring_shifts",
    autoretry_for=(Exception,),
    retry_backoff=True,
    max_retries=2,
    soft_time_limit=60,
    time_limit=90,
)
def materialize_recurring_shifts(_task):
    if not PLANNING_ENABLED:
        return {"status": "disabled"}
    db = SessionLocal()
    try:
        today = datetime.now(MANILA).date()
        created = materialize_work_date(db, today)
        for (region_code,) in db.query(AgentShift.region_code).filter(
            AgentShift.work_date == today,
            AgentShift.is_available.is_(True),
        ).distinct().all():
            enqueue_planning_trigger(db, today, region_code, "manila_workday_rollover")
        db.commit()
        dispatched = dispatch_planning_triggers(db)
        return {"work_date": today.isoformat(), "materialized_shifts": created, "trigger_dispatch": dispatched}
    finally:
        db.close()


@celery_app.task(
    autoretry_for=(Exception,),
    retry_backoff=True,
    max_retries=3,
)
def process_investigation(investigation_id: int):
    db = SessionLocal()

    try:
        investigation = (
            db.query(Investigation)
            .filter(
                Investigation.id == investigation_id,
                Investigation.deleted_at.is_(None),
            )
            .with_for_update()
            .first()
        )

        if investigation is None:
            return {
                "status": "skipped",
                "message": "Investigation not found or deleted",
            }

        if investigation.status == "in_progress":
            return {
                "investigation_id": investigation.id,
                "status": investigation.status,
            }

        if not is_valid_status_transition(investigation.status, "in_progress"):
            return {
                "status": "failed",
                "message": f"Investigation cannot move from {investigation.status} to in_progress",
            }

        investigation.status = "in_progress"

        db.commit()
        db.refresh(investigation)

        print(f"Processing investigation {investigation.id}")

        return {
            "investigation_id": investigation.id,
            "status": "in_progress",
        }

    finally:
        db.close()


@celery_app.task(
    bind=True,
    name="app.workers.tasks.optimize_planning_run",
    autoretry_for=(RetryablePlanningFailure,),
    retry_backoff=True,
    max_retries=2,
    soft_time_limit=270,
    time_limit=300,
)
def optimize_planning_run(task, run_id: int):
    db = SessionLocal()
    try:
        existing = db.query(PlanningRun).filter(PlanningRun.id == run_id).first()
        if existing is None:
            return {"run_id": run_id, "status": "missing"}
        if existing.status == "running":
            started = existing.started_at
            age = (
                (datetime.now(timezone.utc) - (started if started.tzinfo else started.replace(tzinfo=timezone.utc))).total_seconds()
                if started is not None
                else 331
            )
            if age < 330:
                # Celery can redeliver after worker loss while the persisted run
                # still looks active. Schedule a bounded recheck instead of
                # acknowledging the only delivery and stranding the run.
                delay = max(5, int(331 - age))
                optimize_planning_run.apply_async(args=[run_id], countdown=delay)
                return {"run_id": run_id, "status": "running", "recheck_in_seconds": delay}
            existing.status = "queued"
            existing.started_at = None
            db.commit()
        if not PLANNING_ENABLED:
            run = db.query(PlanningRun).filter(PlanningRun.id == run_id).first()
            if run and run.status == "queued":
                run.status = "failed"
                run.error_code = "planning_disabled"
                run.finished_at = datetime.now(timezone.utc)
                db.commit()
            if run:
                _sync_auto_route_assignments(db, run)
            return {"run_id": run_id, "status": run.status if run else "missing"}

        execute_run(db, run_id)
        run = db.query(PlanningRun).filter(PlanningRun.id == run_id).first()
        transient_errors = {
            "osrm_snap_failed",
            "osrm_table_unavailable",
            "osrm_route_unavailable",
            "vroom_unavailable",
        }
        if run and run.status == "failed" and run.error_code in transient_errors:
            if task.request.retries < task.max_retries:
                run.status = "queued"
                run.error_code = None
                run.started_at = None
                run.finished_at = None
                db.commit()
                _sync_auto_route_assignments(db, run)
                raise RetryablePlanningFailure("A routing dependency is temporarily unavailable")
        if run and run.auto_publish and run.status == "ready":
            items = (
                db.query(PlanningItem)
                .filter(PlanningItem.planning_run_id == run.id)
                .all()
            )
            assigned_agents = {
                item.agent_id
                for item in items
                if item.outcome == "assigned" and item.agent_id is not None
            }
            result_complete = (
                len(items) == len(run.investigation_ids)
                and {item.investigation_id for item in items} == set(run.investigation_ids)
                and all(
                    (item.outcome == "assigned" and item.agent_id is not None)
                    or (item.outcome == "unassigned" and item.agent_id is None)
                    for item in items
                )
            )
            geometry_complete = not assigned_agents or _geometry_complete(db, run.id, assigned_agents)
            incomplete = not result_complete or not geometry_complete
            failure_code = "route_geometry_incomplete" if result_complete and not geometry_complete else "auto_route_incomplete"
            actor = db.get(User, run.requested_by_id)
            if incomplete or actor is None:
                run.status = "failed"
                run.error_code = failure_code if actor is not None else "route_refresh_actor_missing"
                run.finished_at = datetime.now(timezone.utc)
                db.commit()
            else:
                try:
                    apply_run(db, run.id, run.result_digest or "", actor)
                except Exception as error:
                    db.rollback()
                    failed = db.query(PlanningRun).filter(PlanningRun.id == run_id).first()
                    if failed and failed.status == "ready":
                        failed.status = "failed"
                        failed.error_code = (
                            str(error) or "auto_route_publish_failed"
                            if isinstance(error, PlanningConflict)
                            else "auto_route_publish_failed"
                        )
                        failed.finished_at = datetime.now(timezone.utc)
                        db.commit()
        if run:
            _sync_auto_route_assignments(db, run)
            db.refresh(run)
        if (
            run
            and run.auto_publish
            and run.status in {"applied", "stale"}
            and run.auto_replan_requested
        ):
            # Applied runs hand overflow cases to the next batch. A stale run
            # must retry its full current scope because its inputs changed
            # before publication and none of its old results are authoritative.
            excluded = set() if run.status == "stale" else set(run.investigation_ids or [])
            current_agent_ids = {
                agent_id
                for (agent_id,) in db.query(AgentShift.agent_id)
                .join(User, User.id == AgentShift.agent_id)
                .filter(
                    AgentShift.work_date == run.work_date,
                    AgentShift.region_code == run.region_code,
                    AgentShift.is_available.is_(True),
                    User.role == "agent",
                    User.is_active.is_(True),
                )
                .all()
            }
            if current_agent_ids != set(run.agent_ids or []):
                # The active run's agent snapshot no longer reflects today's
                # available shifts. Retry its still-unassigned cases with the
                # current eligible roster instead of excluding them as if they
                # had already been processed for this scope.
                excluded.clear()
            requester = db.get(User, run.requested_by_id)
            if requester is not None:
                queue_automatic_planning(
                    db,
                    run.region_code,
                    requester,
                    run.work_date,
                    auto_assignment_id=run.auto_assignment_id,
                    auto_assignment_ids=run.auto_assignment_ids,
                    exclude_investigation_ids=excluded,
                )
                # Clear the durable follow-up marker only after the next scope
                # is committed. A worker loss or broker error before that point
                # leaves enough state for Celery redelivery to finish the batch.
                run.auto_replan_requested = False
                db.commit()
        return {"run_id": run_id, "status": run.status if run else "missing"}
    finally:
        db.close()
