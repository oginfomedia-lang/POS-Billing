"""Maps config names (development/testing/production) to config classes."""
from pathlib import Path

from dotenv import load_dotenv

# Load backend/.env before the config classes read os.environ.
load_dotenv(Path(__file__).resolve().parents[2] / ".env")

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
