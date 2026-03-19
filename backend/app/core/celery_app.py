from celery import Celery
from app.core.config import settings
from celery.schedules import crontab

celery = Celery(
    "ai_learning",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.REDIS_URL
)

celery.conf.update(task_serializer='json', result_serializer='json', accept_content=['json'])

# Periodic tasks (Celery Beat)
celery.conf.beat_schedule = {
    # ── Alerting ────────────────────────────────────────────────────────────
    'run-alerts-check-every-5-minutes': {
        'task': 'app.core.alerts.run_alerts_check_task',
        'schedule': 300.0,
    },
    # ── Full scheduled retrain every Sunday at 02:00 UTC ────────────────────
    'retrain-agents-weekly': {
        'task': 'app.core.automation.retrain_all_agents_task',
        'schedule': crontab(day_of_week='sunday', hour=2, minute=0),
    },
    # ── Data-driven smart retrain check — runs daily at 03:00 UTC ───────────
    # Only triggers a retrain when ≥100 new ProgressLog rows have accumulated.
    'smart-retrain-check-daily': {
        'task': 'app.core.automation.smart_retrain_check_task',
        'schedule': crontab(hour=3, minute=0),
    },
}
celery.conf.timezone = 'UTC'
