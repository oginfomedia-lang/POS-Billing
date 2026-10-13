"""CloudUploadAttempt — one row per attempt to push a backup file to cloud storage."""
from sqlalchemy import BigInteger, Column, DateTime, ForeignKey, Integer, String, Text

from app.extensions import db
from app.models.base import _now


class CloudUploadAttempt(db.Model):
    __tablename__ = "cloud_upload_attempts"

    id = Column(Integer, primary_key=True)
    backup_run_id = Column(Integer, ForeignKey("backup_runs.id", ondelete="CASCADE"), nullable=False, index=True)
    provider = Column(String(20), nullable=False, default="s3")   # s3 / gcs / azure
    bucket = Column(String(200), nullable=True)
    key = Column(String(500), nullable=True)                       # remote object key / path
    # pending / success / failed
    status = Column(String(20), nullable=False, default="pending")
    bytes_uploaded = Column(BigInteger, nullable=True)
    error_message = Column(Text, nullable=True)
    started_at = Column(DateTime(timezone=True), nullable=False, default=_now)
    completed_at = Column(DateTime(timezone=True), nullable=True)
