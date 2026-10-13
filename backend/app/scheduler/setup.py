"""APScheduler setup — call init_scheduler(app) from the app factory."""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

_scheduler = None


def init_scheduler(app) -> None:
    global _scheduler
    try:
        from apscheduler.schedulers.background import BackgroundScheduler
        from apscheduler.triggers.cron import CronTrigger
    except ImportError:
        logger.warning(
            "APScheduler not installed — automated backups disabled. "
            "Install with: pip install apscheduler"
        )
        return

    from app.scheduler.jobs import run_scheduled_backup, run_scheduled_replication_snapshot

    cron_expr = app.config.get("BACKUP_CRON_SCHEDULE", "0 2 * * *")
    # Parse "minute hour dom month dow" cron format
    parts = cron_expr.split()
    if len(parts) == 5:
        minute, hour, day, month, day_of_week = parts
    else:
        logger.warning("Invalid BACKUP_CRON_SCHEDULE %r — defaulting to 02:00 daily", cron_expr)
        minute, hour, day, month, day_of_week = "0", "2", "*", "*", "*"

    _scheduler = BackgroundScheduler(daemon=True)

    _scheduler.add_job(
        run_scheduled_backup,
        CronTrigger(minute=minute, hour=hour, day=day, month=month, day_of_week=day_of_week),
        args=[app],
        id="scheduled_backup",
        replace_existing=True,
    )

    # Replication snapshots every 5 minutes
    _scheduler.add_job(
        run_scheduled_replication_snapshot,
        "interval",
        minutes=5,
        args=[app],
        id="replication_snapshot",
        replace_existing=True,
    )

    _scheduler.start()
    logger.info("Backup scheduler started (cron=%s)", cron_expr)
