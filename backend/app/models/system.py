"""SystemSetting and BackupRun models.

BackupRun is not modelled yet: it belongs with the backup scripts (scripts/backup), which are still stubs.
"""
from app.extensions import db
from app.models.base import _now


class SystemSetting(db.Model):
    """Key/value settings. Keys and defaults are defined in services/settings_service.py."""

    __tablename__ = "system_settings"

    key = db.Column(db.String(50), primary_key=True)
    value = db.Column(db.Text, nullable=False)
    updated_by = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    updated_at = db.Column(db.DateTime(timezone=True), nullable=False, default=_now, onupdate=_now)
