"""
APScheduler configuration.

Schedules:
  - run_daily_penalty_job  →  every day at 00:01 IST
"""

import logging

import pytz
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

logger = logging.getLogger(__name__)
IST = pytz.timezone("Asia/Kolkata")

_scheduler = BackgroundScheduler(timezone=IST)


def start_scheduler(app):
    """Start the background scheduler and register jobs."""
    if _scheduler.running:
        return

    from services.penalty_service import run_daily_penalty_job

    def _penalty_job_with_context():
        """Run penalty job inside the Flask application context."""
        with app.app_context():
            try:
                run_daily_penalty_job()
            except Exception as exc:
                logger.exception("[Scheduler] Penalty job raised an exception: %s", exc)

    _scheduler.add_job(
        func=_penalty_job_with_context,
        trigger=CronTrigger(hour=0, minute=1, timezone=IST),
        id="daily_penalty_job",
        name="Daily Penalty Calculation (00:01 IST)",
        replace_existing=True,
        misfire_grace_time=3600,   # allow up to 1 hour late execution
    )

    _scheduler.start()
    logger.info("[Scheduler] Started. Penalty job scheduled at 00:01 IST daily.")


def stop_scheduler():
    if _scheduler.running:
        _scheduler.shutdown(wait=False)
