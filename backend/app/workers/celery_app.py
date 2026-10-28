import os

from celery import Celery

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
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    broker_transport_options={"visibility_timeout": 360},
)
