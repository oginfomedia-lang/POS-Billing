"""Scheduled backup jobs — called by APScheduler.

* run_scheduled_backup  - the daily backup at BACKUP_CRON_SCHEDULE (default 22:00).
* run_catchup_backup    - shortly after start-up and then hourly: backs up if the last successful backup is
                          older than BACKUP_CATCHUP_HOURS (default 24), so a shop whose PC is off at 22:00
                          still gets about one backup a day.

Several server processes (e.g. Gunicorn workers) each run these jobs; a PostgreSQL advisory lock plus a
"was there a backup just now?" check makes sure only one of them actually backs up.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

logger = logging.getLogger(__name__)

# pg_try_advisory_lock key shared by every process using this database ("LRBK").
_BACKUP_LOCK_KEY = 0x4C52424B


def run_scheduled_backup(app) -> None:
    """The daily backup. Skipped if another process made one in the last hour (one per worker otherwise)."""
    _backup_if_due(app, "Scheduled backup", min_gap=timedelta(hours=1))


def run_catchup_backup(app) -> None:
    """Backs up only when the last successful backup (scheduled or manual) is too old."""
    hours = int(app.config.get("BACKUP_CATCHUP_HOURS", 24))
    if hours > 0:
        _backup_if_due(app, "Catch-up backup", min_gap=timedelta(hours=hours))


def _backup_if_due(app, label: str, min_gap: timedelta) -> None:
    with app.app_context():
        try:
            from sqlalchemy import text

            from app.extensions import db

            with db.engine.connect() as lock_conn:
                if not lock_conn.execute(text("SELECT pg_try_advisory_lock(:k)"), {"k": _BACKUP_LOCK_KEY}).scalar():
                    logger.info("%s: another process is backing up, skipping.", label)
                    return
                try:
                    last = _last_successful_backup()
                    if last and datetime.now(timezone.utc) - last < min_gap:
                        logger.info("%s: last backup %s is recent enough, skipping.", label, last.isoformat())
                        return
                    if label == "Catch-up backup":
                        logger.info("%s: last backup %s, making one now.", label, last.isoformat() if last else "never")
                    _do_backup()
                finally:
                    lock_conn.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": _BACKUP_LOCK_KEY})
                    lock_conn.commit()
        except Exception:  # noqa: BLE001
            logger.exception("%s failed", label)


def _last_successful_backup() -> datetime | None:
    from app.extensions import db
    from app.models.backup import BackupRun

    return db.session.execute(
        db.select(db.func.max(BackupRun.started_at)).where(BackupRun.status == "success")
    ).scalar_one_or_none()


def _do_backup() -> None:
    """pg_dump, then upload to the VPS (if configured) and delete old backups. Needs an app context."""
    from flask import current_app

    from app.extensions import db
    from app.models.user import User
    from app.services import backup_service

    # Use the first admin user as the "created_by" owner for scheduled runs.
    system_user = db.session.execute(
        db.select(User).filter_by(role="admin").limit(1)
    ).scalar_one_or_none()

    if system_user is None:
        logger.warning("Scheduled backup: no admin user found, skipping.")
        return

    run = backup_service.create_backup(system_user)
    logger.info("Scheduled backup complete: %s (status=%s)", run.filename, run.status)

    # Auto-upload to VPS if configured
    if run.status == "success" and current_app.config.get("VPS_HOST"):
        from app.services import cloud_upload_service
        attempt = cloud_upload_service.upload_backup(run.id, provider="sftp")
        logger.info("Auto VPS upload: backup #%s → %s", run.id, attempt.status)

    # Auto-delete backups older than retention period
    retention_days = current_app.config.get("BACKUP_RETENTION_DAYS", 30)
    cleaned = backup_service.cleanup_old_backups(days=retention_days)
    if cleaned:
        logger.info("Auto-cleanup: removed %s backup(s) older than %s days", cleaned, retention_days)


def run_scheduled_replication_snapshot(app) -> None:
    """Save a replication health snapshot. Runs inside the Flask app context."""
    with app.app_context():
        try:
            from app.services import replication_service
            snap = replication_service.snapshot_replication()
            logger.info(
                "Replication snapshot saved: id=%s healthy=%s lag_bytes=%s",
                snap.id, snap.is_healthy, snap.lag_bytes,
            )
        except Exception:  # noqa: BLE001
            logger.exception("Replication snapshot failed")
