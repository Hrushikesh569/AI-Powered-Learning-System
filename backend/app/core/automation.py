"""
Automation utilities for real-time retraining, model hot-reload, and scaling.
"""
import logging
import os
import subprocess
from datetime import datetime, timedelta, timezone

from celery import shared_task

logger = logging.getLogger(__name__)

# Path to the retrain script, relative to this file's module root (/app/ in Docker)
_RETRAIN_SCRIPT = os.path.join(os.path.dirname(__file__), "..", "..", "retrain_all_agents.py")
_EVAL_RUNNER = os.path.join(os.path.dirname(__file__), "..", "ml", "evaluation", "runner.py")

# Minimum new ProgressLog rows accumulated before triggering an unscheduled retrain
_MIN_NEW_ROWS_FOR_RETRAIN = 100


@shared_task(bind=True, max_retries=2, default_retry_delay=300)
def retrain_all_agents_task(self):
    """Run the full agent retraining pipeline (called by Celery Beat weekly)."""
    try:
        subprocess.run(['python', os.path.abspath(_RETRAIN_SCRIPT)], check=True)
        logger.info("Scheduled retraining complete.")
    except subprocess.CalledProcessError as exc:
        logger.error("Retraining failed: %s", exc)
        raise self.retry(exc=exc)


@shared_task(bind=True, max_retries=2, default_retry_delay=300)
def evaluate_agent_task(self, agent: str = 'schedule', runs: int = 50, state_dim: int = 8):
    """Run the evaluation runner as a subprocess to produce mlflow run artifacts."""
    cmd = ['python', os.path.abspath(_EVAL_RUNNER),
           '--agent', agent, '--runs', str(int(runs)), '--state-dim', str(int(state_dim))]
    try:
        subprocess.run(cmd, check=True)
        logger.info("Evaluation for %s completed.", agent)
    except subprocess.CalledProcessError as exc:
        logger.error("Evaluation for %s failed: %s", agent, exc)
        raise self.retry(exc=exc)


@shared_task
def smart_retrain_check_task():
    """Daily smart check: retrain only when ≥100 new ProgressLog rows have
    accumulated since the last retraining run.

    Uses a tiny state file (/tmp/last_retrain_count.txt) to persist the
    row-count watermark between Celery Beat invocations.
    """
    import asyncio
    from sqlalchemy import func, select
    from app.db.session import AsyncSessionLocal
    from app.db.models import ProgressLog

    _STATE_FILE = "/tmp/last_retrain_count.txt"

    async def _get_count() -> int:
        async with AsyncSessionLocal() as db:
            result = await db.execute(select(func.count(ProgressLog.id)))
            return result.scalar_one()

    current_count = asyncio.get_event_loop().run_until_complete(_get_count())

    # Read watermark
    try:
        with open(_STATE_FILE) as f:
            last_count = int(f.read().strip())
    except (OSError, ValueError):
        last_count = 0

    new_rows = current_count - last_count
    logger.info("smart_retrain_check: %d new ProgressLog rows since last retrain", new_rows)

    if new_rows >= _MIN_NEW_ROWS_FOR_RETRAIN:
        logger.info("Threshold reached (%d >= %d) — triggering retrain.", new_rows, _MIN_NEW_ROWS_FOR_RETRAIN)
        retrain_all_agents_task.delay()
        # Update watermark only after dispatching
        with open(_STATE_FILE, "w") as f:
            f.write(str(current_count))
