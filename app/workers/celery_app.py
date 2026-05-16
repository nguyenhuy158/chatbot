"""Celery application for background jobs."""
from celery import Celery
from celery.schedules import crontab

from app.core.config import settings

celery_app = Celery(
    "chatbot",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
    include=["app.workers.ingestion", "app.workers.scheduled"],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="Asia/Ho_Chi_Minh",
    enable_utc=True,
    task_track_started=True,
    task_time_limit=600,
    task_soft_time_limit=540,
)

celery_app.conf.beat_schedule = {
    "memory-cleanup-daily": {
        "task": "app.workers.scheduled.cleanup_expired_memories",
        "schedule": crontab(hour=3, minute=0),
    },
    "image-cleanup-daily": {
        "task": "app.workers.scheduled.cleanup_stale_images",
        "schedule": crontab(hour=3, minute=30),
    },
    "cost-report-daily": {
        "task": "app.workers.scheduled.send_cost_report",
        "schedule": crontab(hour=9, minute=0),
    },
    "stale-content-weekly": {
        "task": "app.workers.scheduled.scan_stale_documents",
        "schedule": crontab(day_of_week=1, hour=4, minute=0),
    },
    "eval-suite-nightly": {
        "task": "app.workers.scheduled.run_eval_suite",
        "schedule": crontab(hour=2, minute=0),
    },
}
