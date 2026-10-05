"""Development settings (debug on, local database)."""
from app.config.base import BaseConfig


class DevelopmentConfig(BaseConfig):
    ENV_NAME = "development"
    DEBUG = True
