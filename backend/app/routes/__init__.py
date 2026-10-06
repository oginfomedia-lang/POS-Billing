"""Registers all blueprints under /api/v1. Routes contain no business logic."""
from flask import Flask

from app.routes.audit_routes import audit_bp
from app.routes.auth_routes import auth_bp
from app.routes.health_routes import health_bp
from app.routes.product_routes import product_bp
from app.routes.shift_routes import shift_bp
from app.routes.store_routes import store_bp
from app.routes.user_routes import user_bp


def register_blueprints(app: Flask) -> None:
    prefix = app.config["API_PREFIX"]
    app.register_blueprint(health_bp, url_prefix=prefix)
    app.register_blueprint(auth_bp, url_prefix=prefix)
    app.register_blueprint(user_bp, url_prefix=prefix)
    app.register_blueprint(store_bp, url_prefix=prefix)
    app.register_blueprint(audit_bp, url_prefix=prefix)
    app.register_blueprint(shift_bp, url_prefix=prefix)
    app.register_blueprint(product_bp, url_prefix=prefix)
