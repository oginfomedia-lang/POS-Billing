"""GET /api/v1/health - lets counters check that the server and database are reachable."""
from datetime import datetime, timezone

from flask import Blueprint, current_app, jsonify
from sqlalchemy import text

from app.extensions import db

health_bp = Blueprint("health", __name__)


@health_bp.get("/health")
def health():
    try:
        db.session.execute(text("SELECT 1"))
        database = "up"
    except Exception:
        current_app.logger.exception("Health check: database unreachable")
        db.session.rollback()
        database = "down"

    body = {
        "status": "ok" if database == "up" else "degraded",
        "database": database,
        "server_time": datetime.now(timezone.utc).isoformat(),
    }
    return jsonify(body), 200 if database == "up" else 503
