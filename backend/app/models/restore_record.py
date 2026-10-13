"""RestoreRecord — one row per database restore operation."""
from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text

from app.extensions import db
from app.models.base import _now


class RestoreRecord(db.Model):
    __tablename__ = "restore_records"

    id = Column(Integer, primary_key=True)
    backup_run_id = Column(Integer, ForeignKey("backup_runs.id", ondelete="SET NULL"), nullable=True, index=True)
    target_db = Column(String(200), nullable=False)
    # running / success / failed
    status = Column(String(20), nullable=False, default="running")
    triggered_by_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    safety_backup_path = Column(String(1000), nullable=True)  # path to pre-restore safety dump
    error_message = Column(Text, nullable=True)
    started_at = Column(DateTime(timezone=True), nullable=False, default=_now)
    completed_at = Column(DateTime(timezone=True), nullable=True)
