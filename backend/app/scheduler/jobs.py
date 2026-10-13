"""Scheduled backup jobs — called by APScheduler."""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def run_scheduled_backup(app) -> None:
    """Create a pg_dump backup. Runs inside the Flask app context."""
    with app.app_context():
        try:
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
        except Exception:  # noqa: BLE001
            logger.exception("Scheduled backup failed")


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
