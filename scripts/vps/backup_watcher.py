"""Keeps the website's backup_runs table in step with client backups uploaded to the VPS (/backups/pos).

Runs on the VPS as the pos-backup-watcher systemd service:
    /root/POS-Billing/backend/venv/bin/python /root/POS-Billing/backend/backup_watcher.py

Every 15 s it
  * registers new  pos_<shop-code>_<YYYYMMDD>_<HHMMSS>.pgdump  files (the time in the name is UTC; older
    pos_db_<date>_<time>.pgdump names from before the shop code are understood too), and
  * marks rows "deleted" when their file has gone (LiteRetailer removes VPS copies older than 30 days).

It logs in with DATABASE_URL from /root/POS-Billing/backend/.env (the same login as the website) and talks
to PostgreSQL directly: it does not start the Flask app, so no extra backup scheduler runs inside it.

    backup_watcher.py          watch forever
    backup_watcher.py --once   one pass, then exit (for testing)
"""
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import psycopg
from dotenv import load_dotenv

BACKUP_DIR = Path("/backups/pos")
ENV_FILE = Path("/root/POS-Billing/backend/.env")
INTERVAL_SECONDS = 15
RETRY_SECONDS = 60

# pos_sharma-mart-420bef_20261017_163000.pgdump  /  pos_db_20261017_163000.pgdump (before shop codes)
NAME = re.compile(r"^pos_(?:(?P<shop>[a-z0-9-]+)_)?(?P<date>\d{8})_(?P<time>\d{6})\.pgdump$")
LEGACY_SHOP = "db"


def log(msg: str) -> None:
    print(f"{datetime.now():%Y-%m-%d %H:%M:%S} {msg}", flush=True)


def database_url() -> str:
    load_dotenv(ENV_FILE, override=True)
    url = os.environ.get("DATABASE_URL", "")
    if not url:
        raise RuntimeError(f"DATABASE_URL is not set in {ENV_FILE}")
    # SQLAlchemy style "postgresql+psycopg://" -> libpq style "postgresql://"
    return url.replace("postgresql+psycopg2://", "postgresql://").replace("postgresql+psycopg://", "postgresql://")


def describe(f: Path) -> tuple[str, datetime]:
    """(shop code or "unknown shop", backup time in UTC) from the filename; file time if it doesn't match."""
    m = NAME.match(f.name)
    if not m:
        return "unknown shop", datetime.fromtimestamp(f.stat().st_mtime, timezone.utc)
    shop = m["shop"] if m["shop"] and m["shop"] != LEGACY_SHOP else "unknown shop"
    when = datetime.strptime(m["date"] + m["time"], "%Y%m%d%H%M%S").replace(tzinfo=timezone.utc)
    return shop, when


def register_new(cur, files: dict[str, Path]) -> None:
    cur.execute("SELECT filename FROM backup_runs WHERE filename = ANY(%s)", (list(files),))
    known = {row[0] for row in cur.fetchall()}
    for name in sorted(set(files) - known):
        f = files[name]
        shop, when = describe(f)
        size = f.stat().st_size
        # The model's defaults live in Python, so every NOT NULL column is filled here.
        cur.execute(
            """INSERT INTO backup_runs
                   (filename, file_path, file_size_bytes, status, storage_location, verified,
                    restore_tested, download_count, started_at, completed_at)
               VALUES (%s, %s, %s, 'success', 'local', false, false, 0, %s, %s)
               ON CONFLICT (filename) DO NOTHING""",
            (name, str(f), size, when, datetime.fromtimestamp(f.stat().st_mtime, timezone.utc)),
        )
        if cur.rowcount:
            log(f"Registered {name} (shop: {shop}, {size:,} bytes, backup time {when:%Y-%m-%d %H:%M} UTC)")


def mark_removed(cur, files: dict[str, Path]) -> None:
    """Client backups whose file is no longer in the folder. Only rows this watcher could have made:
    file in /backups/pos (or no path, from the old watcher) and a pos_*.pgdump name - never the website's own."""
    cur.execute(
        r"""UPDATE backup_runs SET status = 'deleted', file_path = NULL
            WHERE status <> 'deleted'
              AND filename LIKE 'pos\_%%.pgdump'
              AND (file_path LIKE %s OR file_path IS NULL)
              AND NOT (filename = ANY(%s))
            RETURNING filename""",
        (_like_prefix(str(BACKUP_DIR) + os.sep), list(files)),
    )
    for (name,) in cur.fetchall():
        log(f"Marked deleted (file no longer on the server): {name}")


def _like_prefix(text: str) -> str:
    """LIKE pattern for "starts with text" (backslash, % and _ are special in LIKE)."""
    return text.replace("\\", "\\\\").replace("%", r"\%").replace("_", r"\_") + "%"


def sync(conn) -> None:
    if not BACKUP_DIR.is_dir():
        return  # never mark everything deleted because the folder is missing / unmounted
    files = {f.name: f for f in BACKUP_DIR.glob("*.pgdump") if f.is_file()}
    with conn.cursor() as cur:
        if files:
            register_new(cur, files)
        mark_removed(cur, files)
    conn.commit()


def main() -> None:
    once = "--once" in sys.argv
    log(f"Backup watcher started (folder {BACKUP_DIR}, every {INTERVAL_SECONDS}s)")
    while True:
        try:
            with psycopg.connect(database_url(), connect_timeout=10) as conn:
                while True:
                    sync(conn)
                    if once:
                        return
                    time.sleep(INTERVAL_SECONDS)
        except Exception as exc:  # noqa: BLE001 - keep watching; report and wait instead of looping hot
            log(f"Watcher error: {str(exc).splitlines()[0]} (retrying in {RETRY_SECONDS}s)")
            if once:
                sys.exit(1)
            time.sleep(RETRY_SECONDS)


if __name__ == "__main__":
    main()
