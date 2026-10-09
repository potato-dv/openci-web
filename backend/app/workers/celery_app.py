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