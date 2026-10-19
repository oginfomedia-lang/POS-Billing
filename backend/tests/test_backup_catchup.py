"""Catch-up backup: runs only when the last successful backup is too old, and never twice at once."""
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import text

from app.extensions import db
from app.models.backup import BackupRun
from app.scheduler import jobs


@pytest.fixture
def backups_made(monkeypatch):
    """Replaces the real pg_dump + upload with a counter."""
    calls = []
    monkeypatch.setattr(jobs, "_do_backup", lambda: calls.append(1))
    return calls


def add_backup(hours_ago: float, status: str = "success") -> None:
    db.session.add(BackupRun(filename=f"pos_test_{hours_ago}_{status}.pgdump", status=status,
                             started_at=datetime.now(timezone.utc) - timedelta(hours=hours_ago)))
    db.session.commit()


def test_catchup_when_never_backed_up(app, backups_made):
    jobs.run_catchup_backup(app)
    assert len(backups_made) == 1


def test_catchup_when_last_backup_is_old(app, backups_made):
    add_backup(hours_ago=30)
    add_backup(hours_ago=1, status="failed")  # a failed run doesn't count
    jobs.run_catchup_backup(app)
    assert len(backups_made) == 1


def test_no_catchup_when_recent(app, backups_made):
    add_backup(hours_ago=5)
    jobs.run_catchup_backup(app)
    assert backups_made == []


def test_catchup_switched_off(app, backups_made):
    app.config["BACKUP_CATCHUP_HOURS"] = 0
    try:
        jobs.run_catchup_backup(app)
    finally:
        app.config["BACKUP_CATCHUP_HOURS"] = 24
    assert backups_made == []


def test_daily_backup_runs_once_per_hour_across_workers(app, backups_made):
    add_backup(hours_ago=20)
    jobs.run_scheduled_backup(app)
    assert len(backups_made) == 1
    add_backup(hours_ago=0)  # what the first worker's backup leaves behind
    jobs.run_scheduled_backup(app)  # a second worker at the same time
    assert len(backups_made) == 1


def test_skipped_while_another_process_is_backing_up(app, backups_made):
    with app.app_context(), db.engine.connect() as other:
        other.execute(text("SELECT pg_advisory_lock(:k)"), {"k": jobs._BACKUP_LOCK_KEY})
        try:
            jobs.run_catchup_backup(app)
        finally:
            other.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": jobs._BACKUP_LOCK_KEY})
    assert backups_made == []
