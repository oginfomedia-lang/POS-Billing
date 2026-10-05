"""Registers all blueprints under /api/v1. Routes contain no business logic."""
from flask import Flask

from app.routes.health_routes import health_bp


def register_blueprints(app: Flask) -> None:
    prefix = app.config["API_PREFIX"]
    app.register_blueprint(health_bp, url_prefix=prefix)
