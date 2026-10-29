# PyInstaller spec: freezes the backend into dist/literetailer-backend/literetailer-backend.exe.
# Build:  .venv\Scripts\pyinstaller literetailer-backend.spec --noconfirm
# The folder is copied into the installer as resources\backend (see frontend/electron-builder.yml).
import os
from pathlib import Path

from PyInstaller.utils.hooks import collect_all

datas = [
    ("migrations", "migrations"),            # env.py, alembic.ini, versions/ for `setup` / `flask db upgrade`
    ("app/assets", "app/assets"),            # e-bill PDF fonts
    ("backend.env.template", "."),          # filled in by `setup`
]
# Build-time secrets (VPS login ...), not in git; setup copies them into the client's backend.env.
if os.path.exists("backend.secrets.env"):
    datas.append(("backend.secrets.env", "."))
binaries = []
# Every module under app\, from the files themselves. Not collect_submodules("app"): pyinstaller.exe can't import
# `app` (backend\ isn't on its path), so that silently returned nothing and modules nothing else imports
# (app.utils.migration_guards, used only by migrations) were left out.
app_modules = sorted(
    ".".join(p.with_suffix("").parts).removesuffix(".__init__") for p in Path("app").rglob("*.py")
)
hiddenimports = app_modules + [
    "waitress",
    "apscheduler.schedulers.background",
    "apscheduler.triggers.cron",
    "apscheduler.triggers.interval",
    "apscheduler.executors.pool",
    "apscheduler.jobstores.memory",
    "logging.config",
]
# Packages with native parts / data files that PyInstaller does not find on its own.
for pkg in ("psycopg", "psycopg_binary", "uharfbuzz", "fpdf", "cryptography", "paramiko",
            "indic_transliteration"):  # its scripts are .toml data files
    d, b, h = collect_all(pkg)
    datas += d
    binaries += b
    hiddenimports += h

a = Analysis(
    ["literetailer_backend.py"],
    pathex=["."],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=["pytest", "tkinter"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="literetailer-backend",
    console=True,   # the installer reads its output; the service runs it with no window
    icon="../frontend/build/icon.ico",
)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="literetailer-backend")
