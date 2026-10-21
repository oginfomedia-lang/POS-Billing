"""Restore service — runs pg_restore against a target database with a safety pre-backup."""
from __future__ import annotations

import os
import re
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import unquote, urlparse

from flask import current_app
from sqlalchemy import text

from app.errors.exceptions import BadRequestError, NotFoundError
from app.extensions import db
from app.models.backup import BackupRun
from app.models.restore_record import RestoreRecord
from app.models.user import User
from app.services import audit_service


def _pg_binary(name: str) -> str:
    pgbin = current_app.config.get("PGBIN") or os.environ.get("PGBIN", "")
    if pgbin:
        return str(Path(pgbin) / name)
    return name


def _parse_db_url(url: str) -> dict:
    clean = (
        url.replace("postgresql+psycopg://", "postgresql://")
           .replace("postgresql+psycopg2://", "postgresql://")
    )
    parsed = urlparse(clean)
    return {
        "host": parsed.hostname or "localhost",
        "port": str(parsed.port or 5432),
        "user": parsed.username or "postgres",
        "password": unquote(parsed.password or ""),
        "dbname": parsed.path.lstrip("/"),
    }


DB_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,62}$")
# A restore still "running" after this long was cut off (server stopped / PC switched off).
STALE_AFTER = timedelta(hours=1)


def current_db_name() -> str:
    """The database this server uses (literetailer_db on an installed shop, pos_db in development)."""
    return _parse_db_url(current_app.config["SQLALCHEMY_DATABASE_URI"])["dbname"]


def _check_target(target_db: str) -> None:
    live = current_db_name()
    if not DB_NAME.match(target_db):
        raise BadRequestError(f'"{target_db}" is not a valid database name. This shop\'s database is "{live}".')
    exists = db.session.execute(text("SELECT 1 FROM pg_database WHERE datname = :n"), {"n": target_db}).first()
    if not exists:
        raise BadRequestError(f'Database "{target_db}" does not exist on this server. This shop\'s database is "{live}".')


def _safety_dump(target_db: str, backup_dir: Path) -> str:
    """Take a pg_dump of target_db before overwriting it. Returns file path."""
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    filename = f"safety_{target_db}_{ts}.pgdump"
    out_path = backup_dir / filename

    p = _parse_db_url(current_app.config["SQLALCHEMY_DATABASE_URI"])
    env = os.environ.copy()
    env["PGPASSWORD"] = p["password"]

    result = subprocess.run(
        [
            _pg_binary("pg_dump"), "-Fc",
            "-h", p["host"], "-p", p["port"], "-U", p["user"],
            "-d", target_db, "-f", str(out_path),
        ],
        env=env, capture_output=True, text=True, timeout=600,
    )
    if result.returncode != 0:
        raise BadRequestError(
            "Safety pre-restore dump failed: " + (result.stderr or "")[:500]
        )
    return str(out_path)


def restore_backup(backup_run_id: int, target_db: str, user: User) -> RestoreRecord:
    target_db = (target_db or "").strip()
    if not target_db:
        raise BadRequestError("target_db is required.")
    _check_target(target_db)

    run = db.session.get(BackupRun, backup_run_id)
    if not run:
        raise NotFoundError(f"Backup #{backup_run_id} not found.")
    if run.status != "success" or not run.file_path:
        raise BadRequestError("Only a successful backup can be restored.")

    source_path = Path(run.file_path)
    if not source_path.exists():
        raise BadRequestError("Backup file is missing from disk.")

    # Save primitives — pg_restore will wipe the DB so ORM objects become stale
    triggered_by_id = user.id

    record = RestoreRecord(
        backup_run_id=backup_run_id,
        target_db=target_db,
        status="running",
        triggered_by_id=triggered_by_id,
    )
    db.session.add(record)
    db.session.commit()
    record_id, started_at = record.id, record.started_at

    safety_path = None
    restore_status = "failed"
    restore_error = None

    try:
        from app.services.backup_service import _backup_dir
        safety_path = _safety_dump(target_db, _backup_dir())

        p = _parse_db_url(current_app.config["SQLALCHEMY_DATABASE_URI"])
        env = os.environ.copy()
        env["PGPASSWORD"] = p["password"]

        result = subprocess.run(
            [
                _pg_binary("pg_restore"),
                "--clean", "--if-exists",
                "-h", p["host"], "-p", p["port"], "-U", p["user"],
                "-d", target_db,
                str(source_path),
            ],
            env=env, capture_output=True, text=True, timeout=600,
        )

        if result.returncode != 0:
            restore_error = (result.stderr or result.stdout or "pg_restore failed")[:2000]
        else:
            restore_status = "success"

    except Exception as exc:  # noqa: BLE001
        restore_error = str(exc)[:2000]

    try:
        db.session.rollback()
    except Exception:  # noqa: BLE001
        pass
    db.session.expunge_all()

    # A restore of this server's own database drops and recreates every table, so the row added above may be gone
    # (and a row from the backup may now have its id). Finish our row if it is still there, else add a new one.
    record = db.session.get(RestoreRecord, record_id)
    if record is None or (record.status, record.started_at, record.target_db) != ("running", started_at, target_db):
        record = RestoreRecord(backup_run_id=backup_run_id, target_db=target_db, triggered_by_id=triggered_by_id)
        db.session.add(record)
    record.status = restore_status
    record.safety_backup_path = safety_path
    record.completed_at = datetime.now(timezone.utc)
    record.error_message = restore_error
    db.session.commit()

    try:
        fresh_user = db.session.get(User, triggered_by_id) or user
        audit_service.log(
            fresh_user, "backup.restore", "restore_record", record.id,
            new_values={"backup_run_id": backup_run_id, "target_db": target_db, "status": record.status},
        )
        db.session.commit()
    except Exception:  # noqa: BLE001
        pass

    return record


def _close_stale() -> None:
    """Restores left "running" (the server stopped mid-way, or an older version left them behind) are failed."""
    cutoff = datetime.now(timezone.utc) - STALE_AFTER
    stale = RestoreRecord.query.filter(RestoreRecord.status == "running", RestoreRecord.started_at < cutoff).all()
    for r in stale:
        r.status = "failed"
        r.completed_at = r.completed_at or datetime.now(timezone.utc)
        r.error_message = r.error_message or "Interrupted: the server stopped before this restore finished."
    if stale:
        db.session.commit()


def list_restores(page: int = 1, per_page: int = 20) -> tuple[list[RestoreRecord], int]:
    _close_stale()
    q = RestoreRecord.query.order_by(RestoreRecord.started_at.desc())
    total = q.count()
    items = q.offset((page - 1) * per_page).limit(per_page).all()
    return items, total


def get_restore(restore_id: int) -> RestoreRecord:
    record = db.session.get(RestoreRecord, restore_id)
    if not record:
        raise NotFoundError(f"Restore record #{restore_id} not found.")
    return record
