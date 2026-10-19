# POS Billing

Supermarket in-store POS/billing system: a central Flask + PostgreSQL server on the store LAN, and an Electron + React app on each billing counter.

```text
Counter 1..5 (Electron POS)  ──LAN──>  Flask API  ──>  PostgreSQL
                                                  └──>  Backup scripts (OS scheduler)
```

See `documentation/` for the architecture, billing flow and backup runbook.

## Requirements

- Python 3.12+
- Node.js 22+
- PostgreSQL 16+ (developed on 18)

## First-time setup

### 1. Database

Run once as the PostgreSQL superuser. Pick a password for the app user:

```powershell
& "C:\Program Files\PostgreSQL\18\bin\psql.exe" -U postgres -v app_password=YOUR_PASSWORD -f database/setup/create_database_and_user.sql
```

This creates the `pos_app` user and the `pos_db` (live) and `pos_test` (tests) databases.

### 2. Backend

```powershell
cd backend
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements-dev.txt
copy .env.example .env
```

Edit `backend/.env` and put the password from step 1 into `DATABASE_URL` and `TEST_DATABASE_URL`.

```powershell
.venv\Scripts\python run.py          # http://localhost:5000/api/v1/health
.venv\Scripts\python -m pytest       # run tests
```

Database schema changes are made only through migrations:

```powershell
.venv\Scripts\flask db migrate -m "describe the change"
.venv\Scripts\flask db upgrade
```

### 3. Frontend (counter app)

```powershell
cd frontend
npm install
npm run dev          # opens the POS window with hot reload
npm run typecheck
npm run build        # production build into out/
npm run dist         # Windows installer into release/
```

The installer writes `C:\ProgramData\LiteRetailer\counter.json` (in development the app uses
`%APPDATA%\LiteRetailer\counter.json` and creates it on first start):

```json
{ "counterCode": "C01", "apiUrl": "http://localhost:5000/api/v1", "printerName": "" }
```

Main PC: `C01` + `localhost`. Counter PC: the code and Main PC IP chosen in the installer.

### Client installer (LiteRetailer-Setup-x.y.z.exe)

Build everything (frozen backend + app + installer) with `scripts\build\build_installer.ps1`.
See [documentation/installer.md](documentation/installer.md).
The status bar at the bottom of the POS window shows whether the server and database are reachable.

## Production server

```powershell
cd backend
.venv\Scripts\python wsgi.py         # Waitress, FLASK_CONFIG ignored (always production)
```

Production refuses to start until `SECRET_KEY` and `JWT_SECRET_KEY` are set to real values in `backend/.env`.
