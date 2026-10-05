"""create_app(config_name): load config, init extensions, register blueprints and error handlers."""
import os

from flask import Flask
from flask_cors import CORS

from app.config import get_config
from app.errors.handlers import register_error_handlers
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
    CORS(app, resources={rf"{app.config['API_PREFIX']}/*": {"origins": app.config["CORS_ORIGINS"]}})

    register_blueprints(app)
    register_error_handlers(app)

    app.logger.info("POS backend started (%s)", config_class.ENV_NAME)
    return app
