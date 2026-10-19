"""Where the backend finds its .env and keeps its data.

In development everything stays in the repo (backend/.env). The installed app (PyInstaller exe under
Program Files) is read-only, so its .env, logs, backups and uploads live in %ProgramData%\\LiteRetailer.
"""
import os
import sys
from pathlib import Path

APP_NAME = "LiteRetailer"


def is_frozen() -> bool:
    """True when running as the installed literetailer-backend.exe."""
    return getattr(sys, "frozen", False)


def data_dir() -> Path:
    """%ProgramData%\\LiteRetailer on Windows — writable by the service and kept across upgrades.
    Elsewhere (e.g. the web portal on a Linux VPS): LITERETAILER_DATA_DIR, default /var/lib/literetailer."""
    if os.name != "nt":
        return Path(os.environ.get("LITERETAILER_DATA_DIR", "/var/lib/literetailer"))
    return Path(os.environ.get("ProgramData", r"C:\ProgramData")) / APP_NAME


def bundle_dir() -> Path:
    """Folder holding the bundled files (migrations, assets): the exe's _internal folder, or backend/ in dev."""
    if is_frozen():
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    return Path(__file__).resolve().parents[2]


def env_file() -> Path:
    """The .env to load: LITERETAILER_ENV_FILE if set, else ProgramData (installed) or backend/.env (dev)."""
    override = os.environ.get("LITERETAILER_ENV_FILE")
    if override:
        return Path(override)
    if is_frozen():
        return data_dir() / "backend.env"
    return Path(__file__).resolve().parents[2] / ".env"
