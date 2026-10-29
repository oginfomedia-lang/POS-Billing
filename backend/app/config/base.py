"""Settings common to all environments."""
import os
from datetime import timedelta

# At least 32 bytes: shorter HMAC keys are weak for HS256 (PyJWT warns about them).
DEV_SECRET = "dev-only-change-me-not-for-production-use"


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
    # Wrong PINs (login, manager approvals): after this many in a row, that user is locked for a while.
    PIN_MAX_FAILURES = int(os.environ.get("PIN_MAX_FAILURES", "5"))
    PIN_LOCK_MINUTES = int(os.environ.get("PIN_LOCK_MINUTES", "5"))

    # Refuse API calls (except /health and /license) until the shop licence is activated.
    # On in production (the installed server); development and tests skip it.
    LICENSE_REQUIRED = os.environ.get("LICENSE_REQUIRED", "0") == "1"

    LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO")
    LOG_FILE = os.environ.get("LOG_FILE") or None
    # Razorpay / Paytm / WhatsApp values below are fallbacks: the admin normally enters them in
    # Settings → Integrations (services/integration_settings_service.py), which wins over .env.
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

    # --- Paytm card machine: saved for a future integration, not used yet ---
    PAYTM_MID = os.environ.get("PAYTM_MID", "")
    PAYTM_CLIENT_ID = os.environ.get("PAYTM_CLIENT_ID", "")
    PAYTM_MERCHANT_KEY = os.environ.get("PAYTM_MERCHANT_KEY", "")
    PAYTM_BASE_URL = os.environ.get("PAYTM_BASE_URL", "")
    PAYTM_MOCK = os.environ.get("PAYTM_MOCK", "1") == "1"

    # --- WhatsApp Business Cloud API (nightly collection summary to the owner, e-bill to the customer) ---
    # Directory where pg_dump files are stored.  Defaults to <project_root>/backups/daily.
    BACKUP_DIR = os.environ.get("BACKUP_DIR") or None
    # VPS only: the folder client shops upload their backups to (scripts/vps/backup_watcher.py registers them).
    CLIENT_BACKUP_DIR = os.environ.get("CLIENT_BACKUP_DIR") or None
    # Full path to the PostgreSQL bin directory (e.g. C:\Program Files\PostgreSQL\16\bin).
    # Leave empty when pg_dump / pg_restore are already on PATH.
    PGBIN = os.environ.get("PGBIN") or None

    # --- S3 cloud backup ---
    AWS_ACCESS_KEY_ID     = os.environ.get("AWS_ACCESS_KEY_ID", "")
    AWS_SECRET_ACCESS_KEY = os.environ.get("AWS_SECRET_ACCESS_KEY", "")
    AWS_S3_BUCKET         = os.environ.get("AWS_S3_BUCKET", "")
    AWS_S3_REGION         = os.environ.get("AWS_S3_REGION", "ap-south-1")
    AWS_S3_PREFIX         = os.environ.get("AWS_S3_PREFIX", "backups/")

    # --- VPS/SFTP backup (your own server) ---
    VPS_HOST              = os.environ.get("VPS_HOST", "")
    VPS_PORT              = int(os.environ.get("VPS_PORT", "22"))
    VPS_USERNAME          = os.environ.get("VPS_USERNAME", "")
    VPS_PASSWORD          = os.environ.get("VPS_PASSWORD", "")
    VPS_SSH_KEY_PATH      = os.environ.get("VPS_SSH_KEY_PATH", "")
    VPS_BACKUP_PATH       = os.environ.get("VPS_BACKUP_PATH", "/backups/pos/")

    # --- Backup scheduler (cron expression: minute hour dom month dow) ---
    BACKUP_CRON_SCHEDULE    = os.environ.get("BACKUP_CRON_SCHEDULE", "0 22 * * *")
    # Backups older than this many days are auto-deleted from local disk and VPS
    BACKUP_RETENTION_DAYS   = int(os.environ.get("BACKUP_RETENTION_DAYS", "30"))
    # Back up as soon as possible (start-up, then hourly checks) when the last backup is older than this.
    # Covers PCs that are switched off at the daily time. 0 = off.
    BACKUP_CATCHUP_HOURS    = int(os.environ.get("BACKUP_CATCHUP_HOURS") or "24")

    # --- Supplier document uploads ---
    UPLOAD_DIR = os.environ.get("UPLOAD_DIR") or None
    UPLOAD_MAX_BYTES = int(os.environ.get("UPLOAD_MAX_BYTES") or str(20 * 1024 * 1024))  # 20 MB

    # --- App updates (services/update_mirror_service.py) ---
    # HTTPS folder holding latest.yml + LiteRetail-Setup-<version>.exe. The Main PC copies new versions from it
    # and serves them to every PC's app at /api/v1/updates. Blank = no automatic updates.
    UPDATE_FEED_URL = os.environ.get("UPDATE_FEED_URL", "")
    # Where the copies are kept. Default: <data dir>/updates (%ProgramData%\LiteRetailer\updates when installed).
    UPDATE_DIR = os.environ.get("UPDATE_DIR") or None
    UPDATE_CHECK_HOURS = int(os.environ.get("UPDATE_CHECK_HOURS") or "6")

    # --- PostgreSQL replication ---
    PG_REPLICA_HOST       = os.environ.get("PG_REPLICA_HOST", "")
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
