"""Celery application configuration."""
from __future__ import annotations

from celery import Celery
from celery.schedules import crontab

from packages.core import get_settings

settings = get_settings()

app = Celery(
    "fnews",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=["apps.worker.tasks"],
)

app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    worker_prefetch_multiplier=1,
)

# ── Beat schedule (periodic tasks) ─────────────────────────────────────────
# Parse cron string "M H dom mon dow"
_cron_parts = settings.briefing_cron.split()
if len(_cron_parts) == 5:
    _m, _h, _dom, _mon, _dow = _cron_parts
else:
    _m, _h, _dom, _mon, _dow = "0", "7", "*", "*", "*"

app.conf.beat_schedule = {
    "ingest-periodically": {
        "task": "apps.worker.tasks.ingest_task",
        "schedule": float(settings.ingestion_interval_minutes) * 60,
    },
    "daily-briefing": {
        "task": "apps.worker.tasks.briefing_task",
        "schedule": crontab(
            minute=_m,
            hour=_h,
            day_of_month=_dom,
            month_of_year=_mon,
            day_of_week=_dow,
        ),
    },
    "alert-check": {
        "task": "apps.worker.tasks.alert_task",
        "schedule": 1800.0,  # every 30 minutes
    },
    "imap-poll": {
        "task": "apps.worker.tasks.imap_poll_task",
        "schedule": 300.0,  # every 5 minutes
    },
    "self-eval": {
        "task": "apps.worker.tasks.eval_task",
        "schedule": 86400.0,  # daily
    },
}
