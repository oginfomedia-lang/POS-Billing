"""create_app(config_name): load config, init extensions, register blueprints and error handlers."""
import os

from flask import Flask
from flask_cors import CORS

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

    app.logger.info("POS backend started (%s)", config_class.ENV_NAME)
    return app


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

    @jwt_manager.revoked_token_loader
    def revoked(jwt_header, jwt_data):
        return error_response(401, "TOKEN_REVOKED", "Token has been revoked.")
