"""Backup service: create pg_dump files, list, download, verify, delete."""
from __future__ import annotations

import hashlib
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import unquote, urlparse

from flask import current_app

from app.errors.exceptions import BadRequestError, NotFoundError
from app.extensions import db
from app.models.backup import BackupRun
from app.models.user import User
from app.services import audit_service


def _backup_dir() -> Path:
    cfg = current_app.config.get("BACKUP_DIR")
    if cfg:
        d = Path(cfg)
    else:
        # Default: <project_root>/backups/daily — four levels up from this file.
        d = Path(__file__).parent.parent.parent.parent / "backups" / "daily"
    d.mkdir(parents=True, exist_ok=True)
    return d


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


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _pg_binary(name: str) -> str:
    """Return pg_dump / pg_restore path, honouring optional PGBIN config."""
    pgbin = current_app.config.get("PGBIN") or os.environ.get("PGBIN", "")
    if pgbin:
        return str(Path(pgbin) / name)
    return name


def create_backup(user: User) -> BackupRun:
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    filename = f"pos_db_{ts}.pgdump"
    backup_dir = _backup_dir()
    file_path = backup_dir / filename

    run = BackupRun(
        filename=filename,
        file_path=str(file_path),
        status="running",
        storage_location="local",
        created_by_id=user.id,
    )
    db.session.add(run)
    db.session.commit()

    try:
        p = _parse_db_url(current_app.config["SQLALCHEMY_DATABASE_URI"])
        env = os.environ.copy()
        env["PGPASSWORD"] = p["password"]

        result = subprocess.run(
            [
                _pg_binary("pg_dump"),
                "-Fc",
                "-h", p["host"],
                "-p", p["port"],
                "-U", p["user"],
                "-d", p["dbname"],
                "-f", str(file_path),
            ],
            env=env,
            capture_output=True,
            text=True,
            timeout=600,
        )

        if result.returncode != 0:
            run.status = "failed"
            run.error_message = (result.stderr or result.stdout or "pg_dump failed")[:2000]
            run.completed_at = datetime.now(timezone.utc)
            db.session.commit()
            return run

        size = file_path.stat().st_size
        checksum = _sha256(file_path)
        run.status = "success"
        run.file_size_bytes = size
        run.checksum_sha256 = checksum
        run.completed_at = datetime.now(timezone.utc)
        db.session.commit()

        audit_service.log(
            user, "backup.create", "backup", run.id,
            new_values={"filename": filename, "size_bytes": size},
        )
        db.session.commit()
        return run

    except subprocess.TimeoutExpired:
        run.status = "failed"
        run.error_message = "pg_dump timed out after 600 seconds."
        run.completed_at = datetime.now(timezone.utc)
        db.session.commit()
        return run

    except Exception as exc:  # noqa: BLE001
        run.status = "failed"
        run.error_message = str(exc)[:2000]
        run.completed_at = datetime.now(timezone.utc)
        db.session.commit()
        return run


def list_backups(page: int = 1, per_page: int = 20) -> tuple[list[BackupRun], int]:
    q = BackupRun.query.order_by(BackupRun.started_at.desc())
    total = q.count()
    items = q.offset((page - 1) * per_page).limit(per_page).all()
    return items, total


def get_backup(backup_id: int) -> BackupRun:
    run = db.session.get(BackupRun, backup_id)
    if not run:
        raise NotFoundError(f"Backup #{backup_id} not found.")
    return run


def get_download_path(backup_id: int) -> tuple[Path, BackupRun]:
    """Return the verified local file path for a successful backup."""
    run = get_backup(backup_id)
    if run.status == "deleted" or not run.file_path:
        raise BadRequestError("This backup file has been deleted.")
    if run.status != "success":
        raise BadRequestError(f"Backup is not available for download (status: {run.status}).")
    path = Path(run.file_path)
    if not path.exists():
        raise BadRequestError("Backup file is missing from the server disk.")
    # Guard against path traversal: file must live inside the backup directory.
    backup_dir = _backup_dir()
    try:
        path.resolve().relative_to(backup_dir.resolve())
    except ValueError:
        raise BadRequestError("Invalid backup file path.")
    return path, run


def verify_backup(backup_id: int, user: User) -> BackupRun:
    run = get_backup(backup_id)
    if run.status != "success" or not run.file_path:
        raise BadRequestError("Only a successful local backup can be verified.")
    path = Path(run.file_path)
    if not path.exists():
        raise BadRequestError("Backup file not found on disk.")

    try:
        env = os.environ.copy()
        result = subprocess.run(
            [_pg_binary("pg_restore"), "--list", str(path)],
            env=env,
            capture_output=True,
            text=True,
            timeout=120,
        )
    except subprocess.TimeoutExpired:
        raise BadRequestError("Verification timed out after 120 seconds.")
    except FileNotFoundError:
        raise BadRequestError("pg_restore not found. Ensure PostgreSQL tools are on PATH or set PGBIN in .env.")

    if result.returncode != 0:
        raise BadRequestError(
            "Verification failed: " + (result.stderr or "pg_restore returned non-zero exit code.")[:500]
        )

    run.verified = True
    run.verified_at = datetime.now(timezone.utc)
    audit_service.log(user, "backup.verify", "backup", run.id)
    db.session.commit()
    return run


def delete_backup(backup_id: int, user: User) -> BackupRun:
    run = get_backup(backup_id)
    if run.status == "deleted":
        raise BadRequestError("Backup is already deleted.")

    if run.file_path:
        p = Path(run.file_path)
        if p.exists():
            p.unlink()

    old_filename = run.filename
    run.status = "deleted"
    run.file_path = None
    audit_service.log(user, "backup.delete", "backup", run.id, old_values={"filename": old_filename})
    db.session.commit()
    return run
