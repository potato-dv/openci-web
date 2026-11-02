import os

from celery import Celery
from celery.schedules import crontab

celery_app = Celery(
    "openci",
    broker=os.getenv(
        "CELERY_BROKER_URL",
        "redis://localhost:6379/0",
    ),
    include=["app.workers.tasks"],
)

# A worker loss must return the planning task to Redis. The planner's hard
# limit is 300 seconds; the broker redelivers after six minutes so the task can
# safely recover a run left in `running` by a killed process.
celery_app.conf.update(
    timezone="Asia/Manila",
    enable_utc=True,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    broker_transport_options={"visibility_timeout": 360},
    beat_schedule={
        "expire-shift-investigations": {
            "task": "app.workers.tasks.expire_shift_investigations",
            "schedule": 60.0,
            "options": {"expires": 55},
        },
        "dispatch-planning-triggers": {
            "task": "app.workers.tasks.dispatch_planning_triggers",
            "schedule": 60.0,
            "options": {"expires": 55},
        },
        "materialize-recurring-shifts": {
            "task": "app.workers.tasks.materialize_recurring_shifts",
            "schedule": crontab(minute=2, hour=0),
            "options": {"expires": 240},
        },
        "reconcile-missing-routes": {
            "task": "app.workers.tasks.reconcile_missing_routes",
            "schedule": 300.0,
            "options": {"expires": 240},
        },
        "prune-expired-auth-sessions": {
            "task": "app.workers.tasks.prune_expired_auth_sessions",
            "schedule": crontab(minute=30, hour=3),
            "options": {"expires": 1800},
        },
    },
)
