import os

from celery import Celery


REDIS_URL = os.getenv(
    "REDIS_URL",
    "redis://localhost:6379/0",
)


celery_app = Celery(
    "bag_counter",
    broker=REDIS_URL,
    backend=REDIS_URL,
)

celery_app.conf.update(
    task_track_started=True,
    result_expires=3600,
)

celery_app.autodiscover_tasks(
    ["app.worker"]
)