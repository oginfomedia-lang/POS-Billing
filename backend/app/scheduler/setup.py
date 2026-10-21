"""APScheduler setup — call init_scheduler(app) from the app factory."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta

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

    from app.scheduler.jobs import (
        run_catchup_backup,
        run_scheduled_backup,
        run_scheduled_replication_snapshot,
        run_update_mirror,
    )

    cron_expr = app.config.get("BACKUP_CRON_SCHEDULE", "0 22 * * *")
    # Parse "minute hour dom month dow" cron format
    parts = cron_expr.split()
    if len(parts) == 5:
        minute, hour, day, month, day_of_week = parts
    else:
        logger.warning("Invalid BACKUP_CRON_SCHEDULE %r — defaulting to 22:00 daily", cron_expr)
        minute, hour, day, month, day_of_week = "0", "22", "*", "*", "*"

    _scheduler = BackgroundScheduler(daemon=True)

    _scheduler.add_job(
        run_scheduled_backup,
        CronTrigger(minute=minute, hour=hour, day=day, month=month, day_of_week=day_of_week),
        args=[app],
        id="scheduled_backup",
        replace_existing=True,
        # Still run if the server was busy / restarting at the exact time (up to 1 hour late, once).
        misfire_grace_time=3600,
        coalesce=True,
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

    # Catch-up: 2 minutes after start-up (server / PC just switched on), then hourly - backs up only when
    # the last backup is older than BACKUP_CATCHUP_HOURS, e.g. because the PC was off at the daily time.
    _scheduler.add_job(
        run_catchup_backup,
        "interval",
        hours=1,
        next_run_time=datetime.now() + timedelta(minutes=2),
        args=[app],
        id="catchup_backup",
        replace_existing=True,
        coalesce=True,
        max_instances=1,
    )

    # App updates: copy a new installer from UPDATE_FEED_URL for the PCs to update from (no-op when blank).
    if app.config.get("UPDATE_FEED_URL"):
        _scheduler.add_job(
            run_update_mirror,
            "interval",
            hours=max(1, int(app.config.get("UPDATE_CHECK_HOURS", 6))),
            next_run_time=datetime.now() + timedelta(minutes=3),
            args=[app],
            id="update_mirror",
            replace_existing=True,
            coalesce=True,
            max_instances=1,
        )

    _scheduler.start()
    logger.info("Backup scheduler started (cron=%s, catch-up after %sh)", cron_expr,
                app.config.get("BACKUP_CATCHUP_HOURS", 24))
