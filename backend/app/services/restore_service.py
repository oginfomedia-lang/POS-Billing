"""Restore service — runs pg_restore against a target database with a safety pre-backup."""
from __future__ import annotations

import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import unquote, urlparse

from flask import current_app

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
    if not target_db:
        raise BadRequestError("target_db is required.")

    run = db.session.get(BackupRun, backup_run_id)
    if not run:
        raise NotFoundError(f"Backup #{backup_run_id} not found.")
    if run.status != "success" or not run.file_path:
        raise BadRequestError("Only a successful backup can be restored.")

    source_path = Path(run.file_path)
    if not source_path.exists():
        raise BadRequestError("Backup file is missing from disk.")

    record = RestoreRecord(
        backup_run_id=backup_run_id,
        target_db=target_db,
        status="running",
        triggered_by_id=user.id,
    )
    db.session.add(record)
    db.session.commit()

    try:
        # 1. Safety dump of the target DB before we overwrite it
        from app.services.backup_service import _backup_dir
        backup_dir = _backup_dir()
        safety_path = _safety_dump(target_db, backup_dir)
        record.safety_backup_path = safety_path
        db.session.commit()

        # 2. Run pg_restore
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
            record.status = "failed"
            record.error_message = (result.stderr or result.stdout or "pg_restore failed")[:2000]
        else:
            record.status = "success"

        record.completed_at = datetime.now(timezone.utc)
        audit_service.log(
            user, "backup.restore", "restore_record", record.id,
            new_values={"backup_run_id": backup_run_id, "target_db": target_db, "status": record.status},
        )
        db.session.commit()

    except Exception as exc:  # noqa: BLE001
        record.status = "failed"
        record.error_message = str(exc)[:2000]
        record.completed_at = datetime.now(timezone.utc)
        db.session.commit()

    return record


def list_restores(page: int = 1, per_page: int = 20) -> tuple[list[RestoreRecord], int]:
    q = RestoreRecord.query.order_by(RestoreRecord.started_at.desc())
    total = q.count()
    items = q.offset((page - 1) * per_page).limit(per_page).all()
    return items, total


def get_restore(restore_id: int) -> RestoreRecord:
    record = db.session.get(RestoreRecord, restore_id)
    if not record:
        raise NotFoundError(f"Restore record #{restore_id} not found.")
    return record
