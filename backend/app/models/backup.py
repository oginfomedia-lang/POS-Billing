"""BackupRun model — one row per pg_dump execution."""
from sqlalchemy import BigInteger, Boolean, Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from app.extensions import db
from app.models.base import _now


class BackupRun(db.Model):
    __tablename__ = "backup_runs"

    id = Column(Integer, primary_key=True)
    filename = Column(String(200), unique=True, nullable=False)
    file_path = Column(String(1000), nullable=True)   # null after deletion
    file_size_bytes = Column(BigInteger, nullable=True)
    checksum_sha256 = Column(String(64), nullable=True)
    # running / success / failed / deleted
    status = Column(String(20), nullable=False, default="running")
    # local / s3 — always local until cloud is configured
    storage_location = Column(String(20), nullable=False, default="local")
    cloud_path = Column(String(500), nullable=True)   # S3 key when uploaded
    error_message = Column(Text, nullable=True)
    verified = Column(Boolean, nullable=False, default=False)
    verified_at = Column(DateTime(timezone=True), nullable=True)
    restore_tested = Column(Boolean, nullable=False, default=False)
    restore_tested_at = Column(DateTime(timezone=True), nullable=True)
    download_count = Column(Integer, nullable=False, default=0)
    started_at = Column(DateTime(timezone=True), nullable=False, default=_now)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    created_by_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    created_by = relationship("User", foreign_keys=[created_by_id])
