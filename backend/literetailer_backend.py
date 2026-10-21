"""LiteRetail backend entry point (frozen into literetailer-backend.exe by PyInstaller).

    literetailer-backend serve                      run the API (Waitress) - used by the Windows service
    literetailer-backend check-pg --host ...        test PostgreSQL superuser details (installer page)
    literetailer-backend setup --host ...           create role + database, write backend.env, migrate, seed
    literetailer-backend write-counter --code C01 --api-url ...   write counter.json (keeps printer settings)
    literetailer-backend task send-ebills           Task Scheduler job (output -> logs\\send-ebills.log)
    literetailer-backend flask <command> ...        any Flask CLI command (send-daily-collection, send-ebills, db ...)

`setup` is safe to run again (upgrade / repair): an existing backend.env keeps its passwords and secrets,
and the default store, counters and admin are only added to an empty database.
"""
from __future__ import annotations

import argparse
import os
import secrets
import sys
from pathlib import Path

from app.utils.paths import bundle_dir, data_dir, env_file

APP_DB = "literetailer_db"
APP_ROLE = "literetailer_app"
DEFAULT_ADMIN_USERNAME = "admin"
DEFAULT_ADMIN_PIN = "admin123"
DEFAULT_COUNTERS = ["C01", "C02", "C03", "C04", "C05"]


# ---------------------------------------------------------------- PostgreSQL (superuser) helpers

def _connect(host: str, port: int, user: str, password: str, dbname: str = "postgres"):
    import psycopg

    return psycopg.connect(host=host, port=port, user=user, password=password, dbname=dbname,
                           connect_timeout=10, autocommit=True)


def cmd_check_pg(args) -> int:
    try:
        with _connect(args.host, args.port, args.user, args.password) as conn:
            version = conn.execute("SHOW server_version").fetchone()[0]
    except Exception as exc:  # noqa: BLE001 - the installer just shows the message
        print(f"Cannot connect to PostgreSQL: {str(exc).splitlines()[0]}")
        return 1
    print(f"OK - PostgreSQL {version}")
    return 0


def _ensure_role_and_db(args, app_password: str) -> None:
    from psycopg import sql

    with _connect(args.host, args.port, args.superuser, args.superpassword) as conn:
        exists = conn.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (APP_ROLE,)).fetchone()
        verb = "ALTER" if exists else "CREATE"
        # DDL can't take bind parameters, so the password is quoted as a literal.
        conn.execute(sql.SQL(verb + " ROLE {} WITH LOGIN PASSWORD {}").format(
            sql.Identifier(APP_ROLE), sql.Literal(app_password)))
        print(f"Database user {APP_ROLE}: {'updated' if exists else 'created'}")

        if conn.execute("SELECT 1 FROM pg_database WHERE datname = %s", (APP_DB,)).fetchone():
            print(f"Database {APP_DB}: already exists")
        else:
            conn.execute(sql.SQL("CREATE DATABASE {} OWNER {} ENCODING 'UTF8' TEMPLATE template0").format(
                sql.Identifier(APP_DB), sql.Identifier(APP_ROLE)))
            print(f"Database {APP_DB}: created")


def _find_pgbin(explicit: str | None) -> str:
    """PostgreSQL bin folder for pg_dump / pg_restore (backups). Newest local installation wins."""
    if explicit and Path(explicit, "pg_dump.exe").exists():
        return explicit
    candidates: list[Path] = []
    try:
        import winreg

        root = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\PostgreSQL\Installations")
        for i in range(winreg.QueryInfoKey(root)[0]):
            with winreg.OpenKey(root, winreg.EnumKey(root, i)) as key:
                candidates.append(Path(winreg.QueryValueEx(key, "Base Directory")[0]) / "bin")
    except OSError:
        pass
    program_files = Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "PostgreSQL"
    if program_files.exists():
        candidates += sorted((p / "bin" for p in program_files.iterdir()), key=lambda p: _version_key(p.parent.name))
    found = [p for p in candidates if (p / "pg_dump.exe").exists()]
    return str(found[-1]) if found else ""


def _version_key(name: str) -> tuple:
    return tuple(int(x) if x.isdigit() else 0 for x in name.split("."))


# ---------------------------------------------------------------- backend.env

def _write_env(path: Path, values: dict[str, str], old: dict[str, str]) -> None:
    """backend.env = template, then build-time secrets (backend.secrets.env, e.g. VPS login), then whatever
    the client's existing backend.env already had (their edits survive upgrades), then `values`."""
    template = Path(bundle_dir(), "backend.env.template").read_text(encoding="utf-8")
    secrets_file = Path(bundle_dir(), "backend.secrets.env")
    kept = {k: v for k, v in old.items() if v}  # a blank old value must not hide a build-time secret
    values = {**_existing_env(secrets_file), **kept, **values}
    lines = []
    written = set()
    for line in template.splitlines():
        key = line.split("=", 1)[0].strip() if "=" in line and not line.lstrip().startswith("#") else None
        lines.append(f"{key}={values[key]}" if key in values else line)
        written.add(key)
    extra = [f"{k}={v}" for k, v in kept.items() if k not in written]
    if extra:
        lines += ["", "# --- Added on this PC ---", *extra]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _existing_env(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    from dotenv import dotenv_values

    return {k: v for k, v in dotenv_values(path).items() if v is not None}


def _app_password_from(env: dict[str, str]) -> str | None:
    url = env.get("DATABASE_URL")
    if not url:
        return None
    from sqlalchemy.engine import make_url

    parsed = make_url(url)
    return parsed.password if parsed.username == APP_ROLE else None


# ---------------------------------------------------------------- setup

def cmd_setup(args) -> int:
    from datetime import datetime

    log_path = data_dir() / "logs" / "setup.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as log:
        console, sys.stdout = sys.stdout, _Tee(sys.stdout, log)
        try:
            print(f"--- setup {datetime.now():%Y-%m-%d %H:%M:%S} host={args.host} port={args.port}")
            return _setup(args, log)
        finally:
            sys.stdout = console


def _setup(args, log) -> int:
    path = env_file()
    old = _existing_env(path)
    app_password = _app_password_from(old) or secrets.token_urlsafe(24)

    try:
        _ensure_role_and_db(args, app_password)
    except Exception as exc:  # noqa: BLE001
        print(f"Database setup failed: {exc}")
        return 1

    data = data_dir()
    for sub in ("logs", "backups/daily", "uploads"):
        (data / sub).mkdir(parents=True, exist_ok=True)

    _write_env(path, {
        "FLASK_CONFIG": "production",
        "DATABASE_URL": f"postgresql+psycopg://{APP_ROLE}:{app_password}@{args.host}:{args.port}/{APP_DB}",
        "SECRET_KEY": old.get("SECRET_KEY") or secrets.token_urlsafe(64),
        "JWT_SECRET_KEY": old.get("JWT_SECRET_KEY") or secrets.token_urlsafe(64),
        "LOG_FILE": str(data / "logs" / "backend.log"),
        "BACKUP_DIR": str(data / "backups" / "daily"),
        "UPLOAD_DIR": str(data / "uploads"),
        "PGBIN": old.get("PGBIN") or _find_pgbin(args.pgbin),
        "HOST": "0.0.0.0",
        "PORT": str(args.app_port),
    }, old)
    print(f"Settings written: {path}")

    # The settings were loaded when `app` was first imported (before backend.env existed), so the
    # migration runs in a fresh process that reads the new file.
    import subprocess

    me = [sys.executable] if getattr(sys, "frozen", False) else [sys.executable, str(Path(__file__).resolve())]
    env = {**os.environ, "LITERETAILER_ENV_FILE": str(path)}
    seed = subprocess.run([*me, "seed", "--store-name", args.store_name], env=env, capture_output=True, text=True)
    log.write(seed.stderr)  # migration details: log only
    print(seed.stdout.strip())
    if seed.returncode != 0:
        return 1
    print("Setup complete.")
    return 0


class _Tee:
    """Writes setup output to the console (read by the installer) and to logs\\setup.log."""

    def __init__(self, *streams):
        self.streams = streams

    def write(self, text: str) -> None:
        for s in self.streams:
            s.write(text)

    def flush(self) -> None:
        for s in self.streams:
            s.flush()


# ---------------------------------------------------------------- counter.json

def cmd_write_counter(args) -> int:
    """Writes counterCode / apiUrl into %ProgramData%\\LiteRetailer\\counter.json, keeping printer settings."""
    import json

    path = data_dir() / "counter.json"
    config = {"counterCode": "C01", "apiUrl": "http://localhost:5000/api/v1",
              "printerName": "", "autoPrint": True, "drawerEnabled": True}
    if path.exists():
        try:
            config.update(json.loads(path.read_text(encoding="utf-8")))
        except (OSError, ValueError):
            pass  # unreadable file: start again from the defaults
    config["counterCode"] = args.code.strip().upper()
    config["apiUrl"] = args.api_url.strip().rstrip("/")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(config, indent=2), encoding="utf-8")
    print(f"Counter {config['counterCode']} -> {config['apiUrl']} ({path})")
    return 0


def cmd_seed(args) -> int:
    """Second half of setup: migrate and add the first data (run by setup in its own process)."""
    os.environ["LITERETAILER_NO_SCHEDULER"] = "1"
    try:
        _migrate_and_seed(args.store_name)
    except Exception as exc:  # noqa: BLE001
        print(f"Database migration / first data failed: {exc}")
        return 1
    return 0


def _migrate_and_seed(store_name: str) -> None:
    from flask_migrate import upgrade

    from app import create_app
    from app.extensions import db
    from app.models.enums import UserRole
    from app.models.store import Counter, Store
    from app.models.user import User
    from app.schemas.store_schemas import CounterCreate, StoreCreate
    from app.schemas.user_schemas import UserCreate
    from app.services import store_service, user_service

    app = create_app("production")
    with app.app_context():
        upgrade(directory=str(bundle_dir() / "migrations"))
        print("Database tables are up to date.")

        if db.session.query(User).count():
            print("Users already exist - first data not added again.")
            return

        store = db.session.query(Store).order_by(Store.id).first()
        if store is None:
            store = store_service.create_store(StoreCreate(name=store_name), actor=None)
        existing = {c.code for c in db.session.query(Counter).all()}
        for code in DEFAULT_COUNTERS:
            if code not in existing:
                store_service.create_counter(store.id, CounterCreate(code=code, label=f"Counter {code[1:]}"), actor=None)
        user_service.create_user(UserCreate(username=DEFAULT_ADMIN_USERNAME, full_name="Administrator",
                                            pin=DEFAULT_ADMIN_PIN, role=UserRole.ADMIN, store_id=store.id), actor=None)
        print(f"Added store '{store.name}', counters {', '.join(DEFAULT_COUNTERS)} and user "
              f"'{DEFAULT_ADMIN_USERNAME}' (PIN {DEFAULT_ADMIN_PIN}).")


# ---------------------------------------------------------------- serve / flask

def cmd_serve(args) -> int:
    from waitress import serve

    from app import create_app

    app = create_app("production")
    # threads: enough for 5 counters plus admin screens.
    serve(app, host=os.environ.get("HOST", "0.0.0.0"), port=int(os.environ.get("PORT", "5000")), threads=16)
    return 0


def cmd_flask(argv: list[str]) -> int:
    os.environ["LITERETAILER_NO_SCHEDULER"] = "1"
    from app import create_app

    app = create_app("production")
    # "flask db ..." must find the bundled migrations folder.
    if len(argv) > 1 and argv[0] == "db" and "--directory" not in argv and "-d" not in argv:
        argv = ["db", argv[1], "--directory", str(bundle_dir() / "migrations"), *argv[2:]]
    # Plain click commands (create-admin, send-ebills ...) need the app context the `flask` launcher normally pushes.
    with app.app_context():
        app.cli.main(args=argv, prog_name="literetailer-backend flask", standalone_mode=True)
    return 0


SCHEDULED_COMMANDS = ("send-daily-collection", "send-ebills")


def cmd_task(name: str) -> int:
    """Run by Task Scheduler: one Flask command, output appended to %ProgramData%\\LiteRetailer\\logs\\<name>.log."""
    from datetime import datetime

    if name not in SCHEDULED_COMMANDS:
        print(f"Unknown task '{name}'. Use one of: {', '.join(SCHEDULED_COMMANDS)}")
        return 2
    # The service owns backend.log (rotating); a second writer would break its rotation on Windows.
    os.environ["LOG_FILE"] = ""
    log_path = data_dir() / "logs" / f"{name}.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as log:
        streams = sys.stdout, sys.stderr
        sys.stdout = sys.stderr = log
        print(f"--- {datetime.now():%Y-%m-%d %H:%M:%S}")
        try:
            return cmd_flask([name])
        except SystemExit as exc:  # click exits when the command finishes
            return exc.code if isinstance(exc.code, int) else 0
        except Exception:  # noqa: BLE001 - keep the traceback in the task log
            import traceback

            traceback.print_exc()
            return 1
        finally:
            sys.stdout, sys.stderr = streams


def main() -> int:
    if len(sys.argv) > 1 and sys.argv[1] == "flask":
        return cmd_flask(sys.argv[2:])
    if len(sys.argv) > 1 and sys.argv[1] == "task":
        return cmd_task(sys.argv[2] if len(sys.argv) > 2 else "")

    parser = argparse.ArgumentParser(prog="literetailer-backend")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("serve", help="Run the API server.")

    check = sub.add_parser("check-pg", help="Test PostgreSQL login details.")
    check.add_argument("--host", default="localhost")
    check.add_argument("--port", type=int, default=5432)
    check.add_argument("--user", default="postgres")
    check.add_argument("--password", required=True)

    setup = sub.add_parser("setup", help="Create the database, write backend.env, migrate and add first data.")
    setup.add_argument("--host", default="localhost")
    setup.add_argument("--port", type=int, default=5432)
    setup.add_argument("--superuser", default="postgres")
    setup.add_argument("--superpassword", required=True)
    setup.add_argument("--pgbin", default=None, help="PostgreSQL bin folder (found automatically if omitted).")
    setup.add_argument("--app-port", type=int, default=5000)
    setup.add_argument("--store-name", default="My Store")

    seed = sub.add_parser("seed", help="Migrate the database in backend.env and add the first data (part of setup).")
    seed.add_argument("--store-name", default="My Store")

    counter = sub.add_parser("write-counter", help="Write counter.json for this PC.")
    counter.add_argument("--code", required=True)
    counter.add_argument("--api-url", required=True)

    sub.add_parser("flask", help="Run a Flask CLI command, e.g. flask send-ebills.")

    args = parser.parse_args()
    return {"serve": cmd_serve, "check-pg": cmd_check_pg, "setup": cmd_setup, "seed": cmd_seed,
            "write-counter": cmd_write_counter}[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
