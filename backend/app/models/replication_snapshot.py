"""ReplicationSnapshot — point-in-time record of PostgreSQL streaming replication health."""
from sqlalchemy import BigInteger, Boolean, Column, DateTime, Float, Integer, String

from app.extensions import db
from app.models.base import _now


class ReplicationSnapshot(db.Model):
    __tablename__ = "replication_snapshots"

    id = Column(Integer, primary_key=True)
    primary_host = Column(String(200), nullable=True)
    standby_host = Column(String(200), nullable=True)
    lag_bytes = Column(BigInteger, nullable=True)
    lag_seconds = Column(Float, nullable=True)
    is_healthy = Column(Boolean, nullable=False, default=False)
    wal_lsn = Column(String(50), nullable=True)   # e.g. "0/3000060"
    captured_at = Column(DateTime(timezone=True), nullable=False, default=_now)
