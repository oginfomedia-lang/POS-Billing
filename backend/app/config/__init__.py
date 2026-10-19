"""Maps config names (development/testing/production) to config classes."""
from dotenv import load_dotenv

from app.utils.paths import env_file

# Load backend/.env (or %ProgramData%\LiteRetailer\backend.env when installed) before the config classes read os.environ.
load_dotenv(env_file())

from app.config.development import DevelopmentConfig  # noqa: E402
from app.config.production import ProductionConfig  # noqa: E402
from app.config.testing import TestingConfig  # noqa: E402

CONFIGS = {
    "development": DevelopmentConfig,
    "testing": TestingConfig,
    "production": ProductionConfig,
}


def get_config(name: str):
    try:
        return CONFIGS[name]
    except KeyError:
        raise RuntimeError(f"Unknown FLASK_CONFIG '{name}'. Use one of: {', '.join(CONFIGS)}") from None
