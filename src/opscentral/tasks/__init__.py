"""Celery tasks for OpsCentral background processing."""

from celery import Celery

from src.opscentral.config import get_settings

settings = get_settings()

# Initialize Celery
celery_app = Celery(
    "opscentral",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=["src.opscentral.tasks.collection"],
)

# Celery configuration
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_time_limit=300,  # 5 minute timeout
    worker_prefetch_multiplier=1,
    # Beat schedule for periodic tasks
    beat_schedule={
        "collect-metrics": {
            "task": "src.opscentral.tasks.collection.collect_metrics",
            "schedule": settings.metrics_collection_interval,
        },
        "collect-alerts": {
            "task": "src.opscentral.tasks.collection.collect_alerts",
            "schedule": settings.alert_collection_interval,
        },
        "run-compliance-scan": {
            "task": "src.opscentral.tasks.collection.run_compliance_scan",
            "schedule": 3600,  # Every hour
        },
        "calculate-health-score": {
            "task": "src.opscentral.tasks.collection.calculate_health",
            "schedule": 300,  # Every 5 minutes
        },
    },
)
