"""Replication monitoring service — queries pg_stat_replication and saves snapshots."""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import text

from app.extensions import db
from app.models.replication_snapshot import ReplicationSnapshot


def get_replication_status() -> dict:
    """
    Query pg_stat_replication on the primary.
    Returns a dict with replication health info; empty standby list if no replica.
    """
    try:
        rows = db.session.execute(text(
            """
            SELECT
                client_addr,
                state,
                sent_lsn,
                write_lsn,
                flush_lsn,
                replay_lsn,
                pg_wal_lsn_diff(sent_lsn, replay_lsn)  AS lag_bytes,
                EXTRACT(EPOCH FROM (now() - reply_time)) AS lag_seconds
            FROM pg_stat_replication
            """
        )).fetchall()
    except Exception as exc:  # noqa: BLE001
        return {"replicas": [], "error": str(exc)}

    replicas = []
    for r in rows:
        replicas.append({
            "client_addr": str(r.client_addr) if r.client_addr else None,
            "state": r.state,
            "sent_lsn": str(r.sent_lsn),
            "replay_lsn": str(r.replay_lsn),
            "lag_bytes": int(r.lag_bytes) if r.lag_bytes is not None else None,
            "lag_seconds": float(r.lag_seconds) if r.lag_seconds is not None else None,
        })

    is_healthy = bool(replicas) and all(
        (r["lag_bytes"] or 0) < 50 * 1024 * 1024  # < 50 MB lag considered healthy
        for r in replicas
    )

    return {
        "replicas": replicas,
        "replica_count": len(replicas),
        "is_healthy": is_healthy,
    }


def snapshot_replication() -> ReplicationSnapshot:
    """Save a point-in-time replication health snapshot."""
    status = get_replication_status()
    replicas = status.get("replicas", [])
    first = replicas[0] if replicas else {}

    snap = ReplicationSnapshot(
        standby_host=first.get("client_addr"),
        lag_bytes=first.get("lag_bytes"),
        lag_seconds=first.get("lag_seconds"),
        is_healthy=status.get("is_healthy", False),
        wal_lsn=first.get("sent_lsn"),
        captured_at=datetime.now(timezone.utc),
    )
    db.session.add(snap)
    db.session.commit()
    return snap
