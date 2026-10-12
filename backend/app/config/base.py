"""Settings common to all environments."""
import os
from datetime import timedelta

DEV_SECRET = "dev-only-change-me"


class BaseConfig:
    ENV_NAME = "base"
    DEBUG = False
    TESTING = False

    API_PREFIX = "/api/v1"

    SECRET_KEY = os.environ.get("SECRET_KEY", DEV_SECRET)

    SQLALCHEMY_DATABASE_URI = os.environ.get("DATABASE_URL")
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    # pool_pre_ping drops dead connections (e.g. after a PostgreSQL restart).
    # 5 counters + admin screens fit comfortably in this pool.
    SQLALCHEMY_ENGINE_OPTIONS = {
        "pool_pre_ping": True,
        "pool_size": 10,
        "max_overflow": 10,
    }

    JWT_SECRET_KEY = os.environ.get("JWT_SECRET_KEY", DEV_SECRET)
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(
        hours=int(os.environ.get("JWT_ACCESS_TOKEN_HOURS", "12"))
    )
    JWT_REFRESH_TOKEN_EXPIRES = timedelta(
        days=int(os.environ.get("JWT_REFRESH_TOKEN_DAYS", "30"))
    )

    CORS_ORIGINS = os.environ.get("CORS_ORIGINS", "*")

    LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO")
    LOG_FILE = os.environ.get("LOG_FILE") or None
    # --- Razorpay (card + UPI) ---
    RAZORPAY_KEY_ID = os.environ.get("RAZORPAY_KEY_ID", "")
    RAZORPAY_KEY_SECRET = os.environ.get("RAZORPAY_KEY_SECRET", "")
    RAZORPAY_POS_BASE_URL = os.environ.get("RAZORPAY_POS_BASE_URL") or "https://demo.ezetap.com/api/3.0/p2padapter"
    RAZORPAY_POS_USERNAME = os.environ.get("RAZORPAY_POS_USERNAME", "")
    RAZORPAY_POS_APP_KEY = os.environ.get("RAZORPAY_POS_APP_KEY", "")
    # 1 = fake gateway for development/tests (no real money, no real machine)
    RAZORPAY_MOCK = os.environ.get("RAZORPAY_MOCK", "0") == "1"
    # A UPI QR closes itself after this many seconds (Razorpay minimum is 120)
    UPI_QR_EXPIRY_SECONDS = int(os.environ.get("UPI_QR_EXPIRY_SECONDS") or "300")  # empty in .env = default

    # --- WhatsApp Business Cloud API (nightly collection summary to the owner, e-bill to the customer) ---
    # Directory where pg_dump files are stored.  Defaults to <project_root>/backups/daily.
    BACKUP_DIR = os.environ.get("BACKUP_DIR") or None
    # Full path to the PostgreSQL bin directory (e.g. C:\Program Files\PostgreSQL\16\bin).
    # Leave empty when pg_dump / pg_restore are already on PATH.
    PGBIN = os.environ.get("PGBIN") or None
    # --- WhatsApp Business Cloud API (nightly collection summary to the owner) ---
    WHATSAPP_TOKEN = os.environ.get("WHATSAPP_TOKEN", "")
    WHATSAPP_PHONE_NUMBER_ID = os.environ.get("WHATSAPP_PHONE_NUMBER_ID", "")
    WHATSAPP_TEMPLATE_NAME = os.environ.get("WHATSAPP_TEMPLATE_NAME") or "daily_collection"
    WHATSAPP_EBILL_TEMPLATE_NAME = os.environ.get("WHATSAPP_EBILL_TEMPLATE_NAME") or "ebill"
    WHATSAPP_TEMPLATE_LANG = os.environ.get("WHATSAPP_TEMPLATE_LANG") or "en"
    # 1 = don't call WhatsApp, just log the message (development/tests)
    WHATSAPP_MOCK = os.environ.get("WHATSAPP_MOCK", "0") == "1"

    @classmethod
    def validate(cls) -> None:
        """Fail fast when a required setting is missing."""
        if not cls.SQLALCHEMY_DATABASE_URI:
            raise RuntimeError("DATABASE_URL is not set. Copy backend/.env.example to backend/.env.")
