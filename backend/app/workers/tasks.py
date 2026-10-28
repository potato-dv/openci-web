from datetime import datetime, timezone

from app.workers.celery_app import celery_app
from app.config.settings import PLANNING_ENABLED
from app.database import SessionLocal
from app.models.investigation import Investigation
from app.models.planning import PlanningItem, PlanningRun
from app.models.user import User
from app.services.investigation import is_valid_status_transition
from app.services.planning import (
    PlanningConflict,
    _geometry_complete,
    apply_run,
    execute_run,
    queue_automatic_planning,
    sync_assignment_route_refresh,
)


class RetryablePlanningFailure(RuntimeError):
    pass


def _sync_auto_route_assignments(db, run: PlanningRun) -> None:
    assignment_ids = run.auto_assignment_ids or ([run.auto_assignment_id] if run.auto_assignment_id else [])
    for assignment_id in assignment_ids:
        sync_assignment_route_refresh(db, assignment_id)


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
        if run and run.auto_publish and run.status == "applied" and run.auto_replan_requested:
            excluded = set(run.investigation_ids or [])
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
