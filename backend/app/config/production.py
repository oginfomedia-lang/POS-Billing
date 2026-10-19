"""Production settings (debug off, values from environment)."""
import os

from app.config.base import DEV_SECRET, BaseConfig


class ProductionConfig(BaseConfig):
    ENV_NAME = "production"
    LICENSE_REQUIRED = os.environ.get("LICENSE_REQUIRED", "1") == "1"

    @classmethod
    def validate(cls) -> None:
        super().validate()
        if cls.SECRET_KEY == DEV_SECRET or cls.JWT_SECRET_KEY == DEV_SECRET:
            raise RuntimeError("Set SECRET_KEY and JWT_SECRET_KEY to long random values in production.")
