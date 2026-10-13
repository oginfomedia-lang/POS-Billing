"""Cloud upload service — pushes a completed backup file to a cloud storage provider."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from flask import current_app

from app.errors.exceptions import BadRequestError, NotFoundError
from app.extensions import db
from app.models.backup import BackupRun
from app.models.cloud_upload import CloudUploadAttempt


def _get_provider(provider: str):
    """Instantiate the requested storage provider from app config."""
    if provider == "s3":
        from app.services.storage.s3 import S3Storage
        bucket = current_app.config.get("AWS_S3_BUCKET", "")
        if not bucket:
            raise BadRequestError("AWS_S3_BUCKET is not configured.")
        return S3Storage(
            bucket=bucket,
            prefix=current_app.config.get("AWS_S3_PREFIX", "backups/"),
            region=current_app.config.get("AWS_S3_REGION", "ap-south-1"),
        )
    raise BadRequestError(f"Unknown storage provider: {provider!r}")


def upload_backup(backup_run_id: int, provider: str = "s3") -> CloudUploadAttempt:
    run = db.session.get(BackupRun, backup_run_id)
    if not run:
        raise NotFoundError(f"Backup #{backup_run_id} not found.")
    if run.status != "success" or not run.file_path:
        raise BadRequestError("Only a successful local backup can be uploaded.")

    path = Path(run.file_path)
    if not path.exists():
        raise BadRequestError("Backup file is missing from disk.")

    attempt = CloudUploadAttempt(
        backup_run_id=backup_run_id,
        provider=provider,
        status="pending",
    )
    db.session.add(attempt)
    db.session.commit()

    try:
        storage = _get_provider(provider)
        attempt.bucket = current_app.config.get("AWS_S3_BUCKET", "")
        attempt.key = current_app.config.get("AWS_S3_PREFIX", "backups/") + run.filename
        remote_url = storage.upload(str(path), run.filename)
        attempt.status = "success"
        attempt.bytes_uploaded = path.stat().st_size
        attempt.completed_at = datetime.now(timezone.utc)
        # Update BackupRun to reflect cloud storage
        run.storage_location = provider
        run.cloud_path = remote_url
        db.session.commit()
    except Exception as exc:  # noqa: BLE001
        attempt.status = "failed"
        attempt.error_message = str(exc)[:2000]
        attempt.completed_at = datetime.now(timezone.utc)
        db.session.commit()

    return attempt


def list_uploads(backup_run_id: int) -> list[CloudUploadAttempt]:
    return (
        CloudUploadAttempt.query
        .filter_by(backup_run_id=backup_run_id)
        .order_by(CloudUploadAttempt.started_at.desc())
        .all()
    )
