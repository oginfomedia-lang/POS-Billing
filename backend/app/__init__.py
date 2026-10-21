"""create_app(config_name): load config, init extensions, register blueprints and error handlers."""
import os

from flask import Flask
from flask_cors import CORS

from app.cli import register_cli
from app.config import get_config
from app.errors.handlers import error_response, register_error_handlers
from app.extensions import db, jwt, migrate
from app.routes import register_blueprints
from app.utils.logging_config import configure_logging


def create_app(config_name: str | None = None) -> Flask:
    config_class = get_config(config_name or os.environ.get("FLASK_CONFIG", "development"))
    config_class.validate()

    app = Flask(__name__)
    app.config.from_object(config_class)

    configure_logging(app)

    db.init_app(app)
    # Import models so Alembic sees every table.
    from app import models  # noqa: F401
    migrate.init_app(app, db, compare_type=True)
    jwt.init_app(app)
    _configure_jwt_handlers(jwt)
    CORS(app, resources={rf"{app.config['API_PREFIX']}/*": {"origins": app.config["CORS_ORIGINS"]}})

    register_blueprints(app)
    register_error_handlers(app)
    _security_headers(app)
    _require_shop_license(app)
    register_cli(app)

    # The installer's one-off commands (setup, flask ...) set LITERETAILER_NO_SCHEDULER so no backup job starts.
    if not app.config.get("TESTING") and not os.environ.get("LITERETAILER_NO_SCHEDULER"):
        from app.scheduler.setup import init_scheduler
        init_scheduler(app)

    app.logger.info("LiteRetail backend started (%s)", config_class.ENV_NAME)
    return app


def _security_headers(app: Flask) -> None:
    """API replies hold bills, customers' mobiles and staff data: never cache them (shared PCs, proxies),
    never let the browser guess another content type, and never show them inside another site's frame."""
    from flask import request

    prefix = app.config["API_PREFIX"]

    @app.after_request
    def add_headers(resp):
        if request.path.startswith(prefix):
            resp.headers.setdefault("X-Content-Type-Options", "nosniff")
            resp.headers.setdefault("X-Frame-Options", "DENY")
            resp.headers.setdefault("Referrer-Policy", "no-referrer")
            if "Cache-Control" not in resp.headers:
                resp.headers["Cache-Control"] = "no-store"
        return resp


def _require_shop_license(app: Flask) -> None:
    """Every counter goes through this server, so checking here covers the whole shop."""
    from flask import request

    from app.services import license_service

    open_paths = {f"{app.config['API_PREFIX']}/{p}" for p in ("health", "license", "license/activate")}

    @app.before_request
    def check_license():
        if not app.config.get("LICENSE_REQUIRED") or request.method == "OPTIONS" or request.path in open_paths:
            return None
        status = license_service.current_status()
        if not status.valid:
            return error_response(403, "LICENSE_REQUIRED",
                                  "This shop's LiteRetail licence is not active. Activate it on any PC.",
                                  status.to_dict())
        return None


def _configure_jwt_handlers(jwt_manager) -> None:
    @jwt_manager.unauthorized_loader
    def unauthorized(reason: str):
        return error_response(401, "UNAUTHORIZED", reason)

    @jwt_manager.expired_token_loader
    def expired(jwt_header, jwt_data):
        return error_response(401, "TOKEN_EXPIRED", "Your session has expired. Please log in again.")

    @jwt_manager.invalid_token_loader
    def invalid(reason: str):
        return error_response(401, "INVALID_TOKEN", reason)

    @jwt_manager.token_in_blocklist_loader
    def session_ended(jwt_header, jwt_data) -> bool:
        from app.services import auth_service
        return auth_service.session_ended(jwt_data)

    @jwt_manager.revoked_token_loader
    def revoked(jwt_header, jwt_data):
        return error_response(
            401, "SESSION_ENDED",
            "Your login was changed by an admin (new PIN, role or store, or the account was turned off). "
            "Please log in again.",
        )
