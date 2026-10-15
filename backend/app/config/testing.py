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
    RAZORPAY_MOCK = True  # no real money, no real machine
    WHATSAPP_MOCK = True  # no real messages
    PAYTM_MOCK = True
