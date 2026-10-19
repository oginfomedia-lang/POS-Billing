# LiteRetailer client installer

One file, `LiteRetailer-Setup-<version>.exe`, installs everything a store needs.

## Building it

```powershell
powershell -ExecutionPolicy Bypass -File scripts\build\build_installer.ps1
```

The script:

1. downloads (once) the PostgreSQL 17 installer and WinSW into `frontend\build\vendor\` (not in git);
2. freezes the backend with PyInstaller (`backend\literetailer-backend.spec`) into `backend\dist\literetailer-backend\`;
3. runs `npm ci`, `npm run typecheck`, `npm run dist` in `frontend\` → `frontend\release\LiteRetailer-Setup-<version>.exe`.

The version comes from `frontend\package.json`.

## What the installer does

| Step | Main PC (server) | Counter PC |
|---|---|---|
| App files → `C:\Program Files\LiteRetailer` | yes | yes |
| PostgreSQL | uses the existing one (asks host / port / admin user / password and tests them), or silently installs the bundled PostgreSQL 17 (asks for a new `postgres` password) | — |
| `literetailer-backend setup` | creates DB user `literetailer_app` and database `literetailer_db`, writes `C:\ProgramData\LiteRetailer\backend.env`, runs all migrations, adds store **My Store**, counters **C01–C05**, user **admin / admin123** | — |
| Windows service **LiteRetailer Server** (WinSW, automatic, restarts on failure) | yes | — |
| Firewall rule *LiteRetailer Server*, TCP 5000 inbound | yes | — |
| Scheduled tasks (SYSTEM): *LiteRetailer Daily Collection* every 15 min, *LiteRetailer E-bill Retry* every 5 min | yes | — |
| Shop licence: one key for the whole shop, issued for the **Main PC's** machine ID; activate on any PC, every counter shares it | kept by the server (`license.json`) | asks the server |
| `counter.json` | `C01`, `http://localhost:5000/api/v1` | chosen code (C02–C05), `http://<Main PC IP>:5000/api/v1` |

Running the installer again (upgrade / repair) keeps `backend.env` secrets and passwords, runs new migrations and
never adds the first data twice. Printer settings in `counter.json` are kept.

Uninstall removes the program, the service, the scheduled tasks and the firewall rule. It **keeps** the database and
`C:\ProgramData\LiteRetailer` (settings, logs, backups).

## Files on the client PC

```
C:\Program Files\LiteRetailer\
  LiteRetailer.exe
  resources\backend\literetailer-backend.exe       (+ _internal\)
  resources\backend\winsw\LiteRetailerServer.exe   (+ .xml)
C:\ProgramData\LiteRetailer\
  backend.env      server settings (readable by Administrators and the service only)
  counter.json     this PC's counter code, server address, printer settings
  license.json     shop licence key (Main PC only; written by the server when activated)
  logs\            backend.log, setup.log, send-daily-collection.log, send-ebills.log, service logs
  backups\daily\   pg_dump backups
  uploads\         supplier documents
```

## After installing

0. Activate the shop licence (licence screen on any PC). The key must be issued for the **Main PC's**
   machine ID, which every PC shows. Counters work as soon as the Main PC's server is licensed.
1. Sign in as **admin / admin123** and change the PIN (Admin → Users → Reset PIN).
2. Admin → Stores: rename **My Store**, add address / GSTIN (printed on bills).
3. Admin → Settings → Integrations: Razorpay / WhatsApp keys, if used.

## Support commands (run as Administrator)

```powershell
cd "C:\Program Files\LiteRetailer\resources\backend"
.\literetailer-backend.exe check-pg --host localhost --port 5432 --user postgres --password ...
.\literetailer-backend.exe setup --superpassword ...          # repair: re-runs migrations, keeps data
.\literetailer-backend.exe write-counter --code C03 --api-url http://192.168.1.10:5000/api/v1
.\literetailer-backend.exe flask create-admin                 # recover access
.\literetailer-backend.exe task send-ebills                    # what the scheduled task runs
sc.exe stop LiteRetailerServer ; sc.exe start LiteRetailerServer
```

Server health: `http://<Main PC IP>:5000/api/v1/health`.
