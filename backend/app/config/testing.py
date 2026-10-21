"""Test settings (separate test PostgreSQL database)."""
import os

from app.config.base import BaseConfig


class TestingConfig(BaseConfig):
    ENV_NAME = "testing"
    TESTING = True
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "TEST_DATABASE_URL",
        "postgresql+psycopg://pos_app:change_me@localhost:5432/pos_test",
    )
    SQLALCHEMY_ENGINE_OPTIONS = {"pool_pre_ping": True}
    # Fixed 32+ byte keys, so tests never depend on (or warn about) the keys in a developer's .env.
    SECRET_KEY = "test-secret-key-0123456789abcdef-0123"
    JWT_SECRET_KEY = "test-jwt-secret-key-0123456789abcdef"
    RAZORPAY_MOCK = True  # no real money, no real machine
    WHATSAPP_MOCK = True  # no real messages
    PAYTM_MOCK = True
