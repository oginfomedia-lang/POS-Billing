"""Restore service — runs pg_restore against a target database with a safety pre-backup, in the background."""
from __future__ import annotations

import os
import re
import subprocess
import threading
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import unquote, urlparse

from flask import current_app
from sqlalchemy import text

from app.errors.exceptions import BadRequestError, ConflictError, NotFoundError
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
# pg_dump / pg_restore give up instead of waiting for ever on a table another connection is using.
LOCK_WAIT = "60s"

# One restore at a time. While it runs it is described here, not in the database: a restore of this server's own
# database drops every table, so asking the database "is a restore running?" would wait for the restore itself.
_lock = threading.Lock()
_active: dict | None = None   # {"id", "target_db", "live", "phase", "started_at"}
_last: dict | None = None     # how the last restore ended (its row may be gone after a restore of the live database)
_thread: threading.Thread | None = None


def current_db_name() -> str:
    """The database this server uses (literetailer_db on an installed shop, pos_db in development)."""
    return _parse_db_url(current_app.config["SQLALCHEMY_DATABASE_URI"])["dbname"]


def status() -> dict:
    """Answered without the database, so it works while the live database is being replaced."""
    with _lock:
        return {"running": _active is not None, "active": dict(_active) if _active else None,
                "last": dict(_last) if _last else None}


def live_restore_running() -> bool:
    return _active is not None and _active["live"]


def wait(timeout: float | None = None) -> None:
    """Until the background restore (if any) has finished. For tests."""
    if _thread is not None:
        _thread.join(timeout)


def _check_target(target_db: str) -> None:
    live = current_db_name()
    if not DB_NAME.match(target_db):
        raise BadRequestError(f'"{target_db}" is not a valid database name. This shop\'s database is "{live}".')
    exists = db.session.execute(text("SELECT 1 FROM pg_database WHERE datname = :n"), {"n": target_db}).first()
    if not exists:
        raise BadRequestError(f'Database "{target_db}" does not exist on this server. This shop\'s database is "{live}".')


def _pg_env() -> tuple[dict, dict]:
    p = _parse_db_url(current_app.config["SQLALCHEMY_DATABASE_URI"])
    env = os.environ.copy()
    env["PGPASSWORD"] = p["password"]
    return p, env


def _safety_dump(target_db: str, backup_dir: Path) -> str:
    """Take a pg_dump of target_db before overwriting it. Returns file path."""
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    filename = f"safety_{target_db}_{ts}.pgdump"
    out_path = backup_dir / filename

    p, env = _pg_env()
    result = subprocess.run(
        [
            _pg_binary("pg_dump"), "-Fc", f"--lock-wait-timeout={LOCK_WAIT}",
            "-h", p["host"], "-p", p["port"], "-U", p["user"],
            "-d", target_db, "-f", str(out_path),
        ],
        env=env, capture_output=True, text=True, timeout=1800,
    )
    if result.returncode != 0:
        raise BadRequestError(
            "Safety pre-restore dump failed: " + (result.stderr or "")[:500]
        )
    return str(out_path)


def restore_backup(backup_run_id: int, target_db: str, user: User) -> RestoreRecord:
    """Checks the request, adds a "running" row and starts the restore in the background; status() follows it."""
    global _active, _thread
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
    user_id = user.id

    with _lock:
        if _active is not None:
            raise ConflictError(f"Restore #{_active['id']} is still running. Wait for it to finish.")
        record = RestoreRecord(backup_run_id=backup_run_id, target_db=target_db, status="running",
                               triggered_by_id=user_id)
        db.session.add(record)
        db.session.commit()
        _active = {"id": record.id, "target_db": target_db, "live": target_db == current_db_name(),
                   "phase": "safety_copy", "started_at": record.started_at.isoformat()}
        # Hand this request's connection back (record stays readable): the restore closes every open connection.
        db.session.close()
        _thread = threading.Thread(
            target=_run, name=f"restore-{record.id}", daemon=True,
            args=(current_app._get_current_object(), record.id, record.started_at, backup_run_id, target_db,
                  source_path, user_id),
        )
        _thread.start()
    return record


def _run(app, record_id, started_at, backup_run_id, target_db, source_path, user_id) -> None:
    global _active, _last
    with app.app_context():
        try:
            outcome = _restore(record_id, started_at, backup_run_id, target_db, source_path, user_id)
        except Exception as exc:  # noqa: BLE001 - status() must still say it ended
            app.logger.exception("Restore #%s failed", record_id)
            outcome = {"id": record_id, "status": "failed", "error_message": str(exc)[:2000]}
        finally:
            db.session.remove()
    with _lock:
        # No error text here (status() needs no login): the restores list shows it.
        _last = {"id": outcome["id"], "status": outcome["status"], "target_db": target_db, "live": _active["live"],
                 "completed_at": datetime.now(timezone.utc).isoformat()}
        _active = None


def _phase(name: str) -> None:
    with _lock:
        if _active is not None:
            _active["phase"] = name


def _end_other_connections(target_db: str) -> None:
    """Connections still open on target_db (this server's idle pool, a screen's request that was under way) hold
    the tables pg_restore must drop, and it would wait for them. Close them."""
    db.session.execute(
        text("SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
             "WHERE datname = :n AND pid <> pg_backend_pid() AND backend_type = 'client backend'"),
        {"n": target_db},
    )
    db.session.commit()
    db.session.remove()
    db.engine.dispose()


def _upgrade_schema() -> None:
    """A backup from an older version has an older database layout: bring it up to this version's."""
    from flask_migrate import upgrade
    upgrade(directory=str(Path(current_app.root_path).parent / "migrations"))


def _restore(record_id, started_at, backup_run_id, target_db, source_path, user_id) -> dict:
    from app.services.backup_service import _backup_dir

    live = target_db == current_db_name()
    safety_path = None
    restore_status = "failed"
    restore_error = None
    try:
        safety_path = _safety_dump(target_db, _backup_dir())

        _phase("restoring")
        _end_other_connections(target_db)
        p, env = _pg_env()
        env["PGOPTIONS"] = f"-c lock_timeout={LOCK_WAIT}"
        # --single-transaction: all or nothing, a failed restore leaves the database as it was.
        # --no-owner / --no-acl: the tables belong to this server's login, whoever owned them where the backup was made.
        result = subprocess.run(
            [
                _pg_binary("pg_restore"),
                "--clean", "--if-exists", "--single-transaction", "--no-owner", "--no-acl",
                "-h", p["host"], "-p", p["port"], "-U", p["user"],
                "-d", target_db,
                str(source_path),
            ],
            env=env, capture_output=True, text=True, timeout=1800,
        )
        if result.returncode != 0:
            restore_error = (result.stderr or result.stdout or "pg_restore failed")[:2000]
        elif live:
            _phase("updating")
            try:
                _upgrade_schema()
                restore_status = "success"
            except Exception as exc:  # noqa: BLE001
                db.session.rollback()
                restore_error = f"Restored, but updating the database to this version failed: {exc}"[:2000]
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
        record = RestoreRecord(
            backup_run_id=backup_run_id if db.session.get(BackupRun, backup_run_id) else None,
            target_db=target_db, triggered_by_id=user_id if db.session.get(User, user_id) else None,
            started_at=started_at,
        )
        db.session.add(record)
    record.status = restore_status
    record.safety_backup_path = safety_path
    record.completed_at = datetime.now(timezone.utc)
    record.error_message = restore_error
    db.session.commit()

    try:
        fresh_user = db.session.get(User, user_id)
        if fresh_user is not None:
            audit_service.log(
                fresh_user, "backup.restore", "restore_record", record.id,
                new_values={"backup_run_id": backup_run_id, "target_db": target_db, "status": record.status},
            )
            db.session.commit()
    except Exception:  # noqa: BLE001
        db.session.rollback()

    return {"id": record.id, "status": record.status, "error_message": record.error_message}


def _close_stale() -> None:
    """Rows still "running" that are not the restore under way were cut off (the server stopped mid-way, or an
    older version left them behind): they are failed."""
    q = RestoreRecord.query.filter(RestoreRecord.status == "running")
    if _active is not None:
        q = q.filter(RestoreRecord.id != _active["id"])
    stale = q.all()
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
