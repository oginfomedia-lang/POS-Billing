# How the one-command installer is built (and how to make one for another app)

This guide explains **every piece** behind this one command:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\build\build_installer.ps1
```

It turns the whole project into **one file**, `frontend\release\LiteRetail-Setup-1.0.0.exe`. That file can install
LiteRetail on a fresh PC, with or without PostgreSQL already there, as a Main PC or as a Counter PC.

The last part, [Recipe: the same installer for another app](#part-9--recipe-the-same-installer-for-another-app),
is a checklist you can follow on your own.

---

## Part 1 — The big picture

### The problem

A shop PC has nothing on it: no Python, no Node.js, no PostgreSQL. The shop owner is not technical.
We need one file they can double-click, after which:

1. the database is installed (or the one already there is used);
2. our server program runs by itself, even after a restart;
3. the billing app opens from a desktop icon;
4. counters can reach the Main PC over the network.

### The idea: five ingredients packed into one file

| # | Ingredient | What it is | Made by |
|---|---|---|---|
| 1 | **Frozen backend** | The Flask server turned into a normal `.exe`, with Python *inside it* | PyInstaller |
| 2 | **Desktop app** | The React screens inside an Electron window | electron-vite + electron-builder |
| 3 | **PostgreSQL installer** | The official PostgreSQL 17 setup file, carried inside ours | downloaded once |
| 4 | **Service wrapper** | WinSW: makes any `.exe` run as a Windows service | downloaded once |
| 5 | **Install script** | Extra installer pages and steps: ask questions, install PostgreSQL, create the database, start the service | NSIS (`installer.nsh`) |

```
 build_installer.ps1  (the one command)
 │
 ├─ 1. download once ──► build\vendor\postgresql\postgresql-17.6-1-windows-x64.exe
 │                       build\vendor\winsw\LiteRetailerServer.exe
 │
 ├─ 2. PyInstaller ────► backend\dist\literetailer-backend\literetailer-backend.exe  (+ _internal\)
 │
 └─ 3. electron-builder ► frontend\release\LiteRetail-Setup-1.0.0.exe
                          contains:  LiteRetail.exe (app)
                                     resources\backend\  (frozen backend + WinSW)
                                     PostgreSQL installer (unpacked only when needed)
                                     installer.nsh logic (pages + install steps)
```

### What happens on the shop PC (short version)

```
Double-click setup
 → choose folder
 → "Main PC or Counter PC?"
     Main PC:   PostgreSQL found?  yes → ask its admin password and test it
                                   no  → ask a new password; install PostgreSQL silently
                copy files → literetailer-backend setup (database, user, settings, tables, first data)
                → Windows service → firewall port 5000 → scheduled tasks → counter.json (C01)
     Counter:   ask the Main PC's IP + counter code → copy files → counter.json
 → desktop icon
```

---

## Part 2 — The build script, line by line

File: `scripts\build\build_installer.ps1`

### 2.1 Settings at the top

```powershell
param([switch]$RequireSigning)
$ErrorActionPreference = 'Stop'

$root     = Resolve-Path (Join-Path $PSScriptRoot '..\..')
$backend  = Join-Path $root 'backend'
$frontend = Join-Path $root 'frontend'
$vendor   = Join-Path $frontend 'build\vendor'
```

- `param([switch]$RequireSigning)`: an optional flag. With it, the build stops if no code-signing certificate is
  set up (use it for real releases).
- `$ErrorActionPreference = 'Stop'`: **any error stops the script**. Without it, PowerShell carries on after an
  error and you get a broken installer without noticing.
- `$PSScriptRoot` is the folder the script is in. From there we work out the project folders, so the script works
  from any current directory.

### 2.2 Download the third-party installers once

```powershell
$pgFile = 'postgresql-17.6-1-windows-x64.exe'
$pgUrl  = "https://get.enterprisedb.com/postgresql/$pgFile"
$winswUrl = 'https://github.com/winsw/winsw/releases/download/v2.12.0/WinSW-x64.exe'

function Get-Once($url, $path) {
    if (Test-Path $path) { return }                 # already downloaded: skip
    New-Item -ItemType Directory -Force (Split-Path $path) | Out-Null
    Invoke-WebRequest -Uri $url -OutFile "$path.part" -UseBasicParsing
    Move-Item "$path.part" $path                    # rename only when complete
}

Get-Once $pgUrl    (Join-Path $vendor "postgresql\$pgFile")
Get-Once $winswUrl (Join-Path $vendor 'winsw\LiteRetailerServer.exe')
```

- **Why download instead of keeping them in git?** The PostgreSQL installer is about 350 MB. Git is not made for
  big binary files, so `build\vendor` is listed in `.gitignore`.
- **Why `.part` and then rename?** If the internet drops halfway, a half file stays as `.part`. The next run does
  not mistake it for a finished download.
- **Why is WinSW renamed to `LiteRetailerServer.exe`?** WinSW looks for an XML file with *its own name*
  (`LiteRetailerServer.xml`) next to itself. The name of the exe chooses the settings file.

### 2.3 Code signing (optional)

```powershell
if ($env:CSC_LINK) { ... certificate file ... }
elseif ($env:LITERETAIL_SIGN_SUBJECT) { ... USB token ... }
elseif ($env:LITERETAIL_SIGN_ENDPOINT) { ... Azure Trusted Signing ... }
elseif ($RequireSigning) { throw 'No code signing configured' }
else { Write-Warning 'UNSIGNED build' }
```

Signing puts your company name on the exe. Without it, Windows SmartScreen shows "Unknown publisher". The build
works either way. Details: `documentation\code-signing.md`.

### 2.4 Freeze the backend (Python → exe)

```powershell
Push-Location $backend
    if (-not (Test-Path '.venv\Scripts\python.exe')) { py -3.13 -m venv .venv }
    & .venv\Scripts\python.exe -m pip install -q -r requirements.txt -r requirements-build.txt
    & .venv\Scripts\pyinstaller.exe literetailer-backend.spec --noconfirm --log-level WARN
    & dist\literetailer-backend\literetailer-backend.exe --help | Out-Null
    if ($LASTEXITCODE) { throw 'Frozen backend does not start' }
    & .venv\Scripts\python.exe (Join-Path $PSScriptRoot 'check_frozen_backend.py')
    if ($LASTEXITCODE) { throw 'Frozen backend is incomplete (see above)' }
Pop-Location
```

Step by step:

1. **Make a virtual environment** (`.venv`) if there isn't one. This is a private Python with only this
   project's libraries.
2. **Install the libraries**, plus `pyinstaller` (from `requirements-build.txt`, needed only for building).
3. **Run PyInstaller** with our recipe file (`.spec`, explained in Part 3).
4. **Smoke test:** run the new exe with `--help`. If it can't even start, stop now, not on the client's PC.
5. **Completeness test:** `check_frozen_backend.py` checks that every `.py` file under `backend\app` is inside
   the exe. We added this after a real failure ("No module named app.utils.migration_guards") that only showed
   up on the client.

> `if ($LASTEXITCODE) { throw ... }`: outside programs (pip, pyinstaller, npm) don't trigger
> `$ErrorActionPreference`. You must check their exit code yourself after every one.

### 2.5 Build the desktop app and the installer

```powershell
Push-Location $frontend
    npm ci                      # exact library versions from package-lock.json
    if (-not (Test-Path 'node_modules\electron\path.txt')) { node node_modules\electron\install.js }
    npm run typecheck           # TypeScript errors stop the build
    npm run dist -- @signArgs   # = electron-vite build && electron-builder --win
Pop-Location
```

- `npm ci` instead of `npm install`: it installs **exactly** what `package-lock.json` says, so every build is the
  same.
- The Electron check repairs a known problem: Electron's program download sometimes fails quietly.
- `npm run dist` (from `package.json`) does two things:
  1. `electron-vite build` compiles the React screens and the Electron main/preload code into `out\`;
  2. `electron-builder --win` packs everything into the NSIS installer, following `electron-builder.yml`
     (Part 4).

### 2.6 Final checks

```powershell
$version = (Get-Content (Join-Path $frontend 'package.json') -Raw | ConvertFrom-Json).version
$setup = Get-Item (Join-Path $frontend "release\LiteRetail-Setup-$version.exe")
# if signed: check each exe really carries a valid signature
Write-Host ("Done: {0} ({1:N0} MB)" -f $setup.FullName, ($setup.Length / 1MB))
```

The version number comes from **`frontend\package.json`**. To release 1.0.1, change it there.

---

## Part 3 — Freezing the backend: `backend\literetailer-backend.spec`

PyInstaller copies the Python interpreter, our code and every library into one folder with an `.exe` that starts
them. The shop PC does **not** need Python installed.

```python
datas = [
    ("migrations", "migrations"),            # database migrations, needed by `setup`
    ("app/assets", "app/assets"),            # fonts for e-bill PDFs
    ("backend.env.template", "."),          # settings template, filled in by `setup`
]
if os.path.exists("backend.secrets.env"):    # build-time secrets, not in git
    datas.append(("backend.secrets.env", "."))
```

**`datas`** are non-Python files to copy along. PyInstaller follows `import` lines to find code, but it can't
know that we read `migrations\` or a font file at runtime. You must list them.

```python
app_modules = sorted(
    ".".join(p.with_suffix("").parts).removesuffix(".__init__") for p in Path("app").rglob("*.py")
)
hiddenimports = app_modules + ["waitress", "apscheduler.schedulers.background", ...]
```

**`hiddenimports`** are modules PyInstaller can't find by following imports, for example code that is loaded
only by name, or used only by migrations. We list **every file under `app\`**, so nothing can be forgotten.

```python
for pkg in ("psycopg", "psycopg_binary", "uharfbuzz", "fpdf", "cryptography", "paramiko"):
    d, b, h = collect_all(pkg)
```

**`collect_all`** takes everything from libraries that carry DLLs or data files PyInstaller misses by itself
(the PostgreSQL driver, PDF fonts, encryption).

```python
a = Analysis(["literetailer_backend.py"], ...)   # start file
exe = EXE(..., name="literetailer-backend", console=True, icon=".../icon.ico")
coll = COLLECT(exe, a.binaries, a.datas, name="literetailer-backend")
```

- `Analysis` starts from `literetailer_backend.py` and follows all imports.
- `console=True`: the installer reads what the exe prints (error messages). The service hides the window anyway.
- `COLLECT` makes a **folder** (`literetailer-backend.exe` + `_internal\`). This starts much faster than
  "one-file" mode, which unpacks itself to a temp folder on every start.

### Where the frozen exe keeps its files: `backend\app\utils\paths.py`

`C:\Program Files\` is **read-only** for normal programs and services. So the installed backend must keep its
settings, logs and backups somewhere else.

```python
def is_frozen() -> bool:
    return getattr(sys, "frozen", False)      # True only inside the PyInstaller exe

def data_dir() -> Path:                        # C:\ProgramData\LiteRetailer
    return Path(os.environ.get("ProgramData", r"C:\ProgramData")) / APP_NAME

def bundle_dir() -> Path:                      # where the packed files (migrations...) are
    if is_frozen():
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    return Path(__file__).resolve().parents[2]   # backend\ in development

def env_file() -> Path:                        # which settings file to read
    if os.environ.get("LITERETAILER_ENV_FILE"): return Path(...)
    if is_frozen(): return data_dir() / "backend.env"
    return backend / ".env"
```

The same code works in development (`backend\.env`) and when installed
(`C:\ProgramData\LiteRetailer\backend.env`). **`ProgramData` survives upgrades and uninstalls**, so the shop's
settings and backups are never lost.

---

## Part 4 — Packing: `frontend\electron-builder.yml`

```yaml
appId: com.litecode.literetailer          # unique ID: lets Windows recognise upgrades of the same app
productName: LiteRetail
artifactName: LiteRetail-Setup-${version}.${ext}
directories:
  output: release
  buildResources: build                   # icon.ico, installer.nsh, vendor\ live here
files:
  - out/**                                # the compiled Electron + React code
  - package.json
extraResources:                           # copied next to the app, outside app.asar
  - from: ../backend/dist/literetailer-backend
    to: backend
  - from: build/vendor/winsw/LiteRetailerServer.exe
    to: backend/winsw/LiteRetailerServer.exe
  - from: build/winsw/LiteRetailerServer.xml
    to: backend/winsw/LiteRetailerServer.xml
```

- **`files`** go inside `app.asar` (a packed archive that only Electron can read).
- **`extraResources`** go to `C:\Program Files\LiteRetail\resources\` as normal files. **Anything Windows must
  run directly (the backend exe, WinSW) must be an extraResource**, because Windows can't run an exe from inside
  `app.asar`.

```yaml
win:
  target: nsis                            # NSIS = the installer engine
nsis:
  oneClick: false                         # show pages (folder, our custom pages)
  perMachine: true                        # install for all users in Program Files -> needs admin
  allowToChangeInstallationDirectory: true
  createDesktopShortcut: always
  deleteAppDataOnUninstall: false         # never delete the shop's data
  include: build/installer.nsh            # <- OUR pages and install steps
publish:
  - provider: generic                     # makes latest.yml for auto-update
    url: http://localhost:5000/api/v1/updates
```

`perMachine: true` matters: installing PostgreSQL, a service and a firewall rule all need **administrator**
rights. The installer asks for them (UAC) once at the start.

`include: build/installer.nsh` is the hook. electron-builder makes a standard installer and then pulls in our file
at fixed points ("macros").

---

## Part 5 — The installer logic: `frontend\build\installer.nsh`

NSIS is a small scripting language for installers. Quick reading guide:

| NSIS | Meaning |
|---|---|
| `Var X` / `$X` | a variable |
| `StrCpy $X "value"` | `X = "value"` |
| `${If} ... ${EndIf}` | if |
| `Function Name ... FunctionEnd` | a function |
| `!macro customX ... !macroend` | code electron-builder runs at a fixed point |
| `nsExec::ExecToStack 'cmd'` then `Pop $0` / `Pop $1` | run a command without a window; `$0` = exit code, `$1` = its output |
| `Abort` | on a page: stay on the page (or skip it when the page is being created); in install: stop |
| `$INSTDIR` | chosen install folder |

### 5.1 The hooks electron-builder gives us

| Macro | When it runs | What we do in it |
|---|---|---|
| `customInit` | installer starts | stop the running service so its files can be replaced |
| `customPageAfterChangeDir` | after "Choose folder" page | add our 3 pages |
| `customInstall` | after files are copied | all the real work |
| `customUnInit` / `customUnInstall` | uninstall | stop/delete the service, tasks, firewall rule (**not** the database) |

### 5.2 Stop the old service first (upgrades)

```nsis
!macro customInit
  nsExec::Exec 'sc.exe stop ${SERVICE_NAME}'
  Pop $0
  ${If} $0 == 0
    Sleep 4000
  ${EndIf}
!macroend
```

A running exe can't be overwritten on Windows. When upgrading, stop the server first and wait 4 seconds for it
to close.

### 5.3 Page 1: Main PC or Counter PC

```nsis
Function SetupTypePageCreate
  ${If} $SetupType == ""             ; first time this page is shown: set defaults
    StrCpy $SetupType "server"
    StrCpy $PgHost "localhost"
    StrCpy $PgPort "5432"
    StrCpy $PgUser "postgres"
    Call DetectPostgres              ; <- is PostgreSQL already here?
  ${EndIf}
  ${NSD_CreateRadioButton} 0 6u 100% 12u "Main PC (server)"
  ${NSD_CreateRadioButton} 0 52u 100% 12u "Counter PC"
  nsDialogs::Show
FunctionEnd

Function SetupTypePageLeave          ; "Next" pressed: remember the choice
  ${NSD_GetState} $hRadioCounter $0
  ${If} $0 == ${BST_CHECKED}
    StrCpy $SetupType "counter"
  ${Else}
    StrCpy $SetupType "server"
  ${EndIf}
FunctionEnd
```

Every custom page has two functions: **Create** draws it, **Leave** reads and checks the answers when Next is
pressed.

### 5.4 Detecting PostgreSQL (the "present or not present" part)

```nsis
Function DetectPostgres
  StrCpy $PgFound 0
  SetRegView 64                                              ; read the 64-bit registry
  EnumRegKey $0 HKLM "SOFTWARE\PostgreSQL\Installations" 0   ; any PostgreSQL installed by the official setup?
  ${If} $0 != ""
    ReadRegStr $PgBase HKLM "SOFTWARE\PostgreSQL\Installations\$0" "Base Directory"   ; its folder (for psql.exe)
    StrCpy $PgFound 1
  ${EndIf}
  EnumRegKey $0 HKLM "SOFTWARE\PostgreSQL\Services" 0
  ${If} $0 != ""
    ReadRegDWORD $1 HKLM "SOFTWARE\PostgreSQL\Services\$0" "Port"                     ; its port
    StrCpy $PgPort $1
    StrCpy $PgFound 1
  ${EndIf}
  ${If} $PgFound == 0                                        ; no registry entry: is something on port 5432?
    nsExec::ExecToStack 'powershell.exe -NoProfile -Command "if (Get-NetTCPConnection -LocalPort 5432 -State Listen -ErrorAction SilentlyContinue) { exit 0 } else { exit 1 }"'
    Pop $0
    ${If} $0 == 0
      StrCpy $PgFound 1
    ${EndIf}
  ${EndIf}
FunctionEnd
```

There are three ways to find it, from most to least reliable:

1. the registry keys the official PostgreSQL installer writes (gives the folder);
2. its service registry key (gives the port);
3. anything listening on port 5432 (covers PostgreSQL installed some other way).

### 5.5 Page 2: the database page (Main PC only), two versions

```nsis
Function PgPageCreate
  ${If} $SetupType != "server"
    Abort                          ; Counter PC: skip this page
  ${EndIf}
  ${If} $PgFound == 1
    ; "PostgreSQL is already installed. Enter its administrator login."  -> Host, Port, User, Password
  ${Else}
    ; "PostgreSQL 17 will be installed." -> choose Password, Confirm, Port
  ${EndIf}
FunctionEnd
```

When Next is pressed (`PgPageLeave`):

- **Password characters checked** (`CheckPasswordChars`): no spaces, `"` or `%`. The password goes on a command
  line, where those characters would break it.
- **PostgreSQL found:** test the login **right now** with that PostgreSQL's own `psql.exe`:

  ```nsis
  System::Call 'Kernel32::SetEnvironmentVariable(t "PGPASSWORD", t "$PgPass")i'
  nsExec::ExecToStack '"$PgBase\bin\psql.exe" -w -h "$PgHost" -p $PgPort -U "$PgUser" -d postgres -t -c "select 1"'
  Pop $0
  Pop $1
  System::Call 'Kernel32::SetEnvironmentVariable(t "PGPASSWORD", p 0)i'   ; clear it again
  ${If} $0 != 0
    MessageBox MB_ICONSTOP "Cannot connect to PostgreSQL with these details:$\r$\n$\r$\n$1"
    Abort                                                                  ; stay on the page
  ${EndIf}
  ```

  A wrong password is caught **on this page**, before anything is installed. The password goes in through the
  `PGPASSWORD` environment variable, not on the command line, and is cleared straight after.
- **PostgreSQL not found:** the two passwords must match, with at least 6 characters.

### 5.6 Page 3: the counter page (Counter PC only)

This page asks for the Main PC's IP address and a counter code (C02–C05). Main PC is always C01.

### 5.7 The install steps (`customInstall`)

These run after the app files are copied. `$R9` = the backend exe, `$R8` = `C:\ProgramData\LiteRetailer`.

**Main PC, PostgreSQL missing: install it silently**

```nsis
${If} $PgFound == 0
  InitPluginsDir
  File "/oname=$PLUGINSDIR\${PG_INSTALLER}" "${BUILD_RESOURCES_DIR}\vendor\postgresql\${PG_INSTALLER}"
  ExecWait '"$PLUGINSDIR\${PG_INSTALLER}" --mode unattended --unattendedmodeui minimal --superpassword "$PgPass" --serverport $PgPort --disable-components pgAdmin,stackbuilder' $0
  Delete "$PLUGINSDIR\${PG_INSTALLER}"
  ${If} $0 != 0
    MessageBox MB_ICONSTOP "PostgreSQL could not be installed (error $0). Run this installer again."
    Abort
  ${EndIf}
${EndIf}
```

- `File "/oname=..."` **packs the PostgreSQL installer inside ours at build time** and unpacks it to a temporary
  folder (`$PLUGINSDIR`) only now, only when needed. Counter PCs never unpack it.
- `--mode unattended`: the official PostgreSQL installer has a silent mode. We pass the password and port the
  user chose on our page. pgAdmin and StackBuilder are left out.
- `ExecWait` waits until it's finished. Exit code not 0 → show the error and stop.

**Main PC: create our database, settings and first data**

```nsis
nsExec::ExecToStack '"$R9" setup --host "$PgHost" --port $PgPort --superuser "$PgUser" --superpassword "$PgPass" --app-port ${APP_PORT}'
Pop $0
Pop $1
${If} $0 != 0
  MessageBox MB_ICONSTOP "The LiteRetail database could not be set up:$\r$\n$\r$\n$1$\r$\nDetails: $R8\logs\setup.log"
  Abort
${EndIf}
```

The hard work is done by **our own exe** (`setup` command, Part 6). NSIS is a poor language for database work;
Python is a good one. So the installer only collects answers and then calls our program.

**Main PC: protect the settings file**

```nsis
nsExec::Exec 'icacls "$R8\backend.env" /inheritance:r /grant:r *S-1-5-18:F *S-1-5-32-544:F'
```

`backend.env` holds the database password and secret keys. After this, only **SYSTEM** (S-1-5-18, the service)
and **Administrators** (S-1-5-32-544) can read it. The SID numbers are used instead of names because names change
with the Windows language.

**Main PC: Windows service**

```nsis
nsExec::Exec 'sc.exe delete ${SERVICE_NAME}'                                         ; remove an old one
nsExec::ExecToStack '"$INSTDIR\resources\backend\winsw\${SERVICE_NAME}.exe" install'  ; WinSW registers it
nsExec::ExecToStack 'sc.exe start ${SERVICE_NAME}'
```

**Main PC: firewall**

```nsis
nsExec::Exec 'netsh advfirewall firewall add rule name="${FIREWALL_RULE}" dir=in action=allow protocol=TCP localport=${APP_PORT}'
```

Without this, Windows Firewall blocks counters from reaching port 5000. The old rule is deleted first, so
reinstalling doesn't create duplicates.

**Main PC: scheduled tasks**

```nsis
nsExec::Exec 'schtasks.exe /Create /F /RU SYSTEM /RL HIGHEST /SC MINUTE /MO 15 /TN "${TASK_DAILY}" /TR "\"$R9\" task send-daily-collection"'
```

Task Scheduler runs `literetailer-backend.exe task send-daily-collection` every 15 minutes as SYSTEM.

**Both PCs: counter.json**

```nsis
nsExec::ExecToStack '"$R9" write-counter --code $CounterCode --api-url "http://$ServerIp:${APP_PORT}/api/v1"'
nsExec::Exec 'icacls "$R8\counter.json" /grant *S-1-5-32-545:M'     ; all users may edit (printer settings)
```

The desktop app reads `C:\ProgramData\LiteRetailer\counter.json` to know which counter it is and where the
server is.

### 5.8 Silent upgrades (auto-update)

```nsis
${If} ${Silent}
  ${If} ${FileExists} "$R8\backend.env"
    nsExec::ExecToStack '"$R9" seed'          ; update the database tables to the new version
    ...write the output to logs\update.log...
    nsExec::Exec '"...\winsw\${SERVICE_NAME}.exe" install'
    nsExec::Exec 'sc.exe start ${SERVICE_NAME}'
  ${EndIf}
${Else}
  ...the normal steps above...
${EndIf}
```

Auto-update runs the new installer with `/S` (silent), so there are no pages and no questions. It keeps the
existing setup and only updates the database tables (`seed` = migrations) and restarts the service.

---

## Part 6 — The backend exe's own commands: `backend\literetailer_backend.py`

This is the **start file** PyInstaller freezes. One exe, several commands:

| Command | Who calls it | What it does |
|---|---|---|
| `serve` | the Windows service | runs the API with Waitress on port 5000 |
| `setup --host ... --superpassword ...` | installer (Main PC) | database user, database, `backend.env`, then `seed` |
| `seed` | `setup`, and silent upgrades | migrations + first data (only on an empty database) |
| `write-counter --code --api-url` | installer (both) | writes `counter.json`, keeps printer settings |
| `check-pg` | (helper) | tests a PostgreSQL login |
| `task <name>` | Task Scheduler | runs one job, output to `logs\<name>.log` |
| `flask <cmd>` | you, for maintenance | any Flask CLI command, e.g. `flask db current` |

### 6.1 `setup`: the most important one

```python
def _setup(args, log) -> int:
    path = env_file()                                  # C:\ProgramData\LiteRetailer\backend.env
    old = _existing_env(path)                          # settings from a previous install, if any
    app_password = _app_password_from(old) or secrets.token_urlsafe(24)

    _ensure_role_and_db(args, app_password)            # 1. database user + database
    for sub in ("logs", "backups/daily", "uploads"):   # 2. data folders
        (data / sub).mkdir(parents=True, exist_ok=True)
    _write_env(path, {...}, old)                       # 3. backend.env
    seed = subprocess.run([*me, "seed", ...], env={..., "LITERETAILER_ENV_FILE": str(path)})   # 4. tables + data
```

**1. `_ensure_role_and_db`**, using the PostgreSQL **admin** login that was typed on the installer page:

```python
exists = conn.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (APP_ROLE,)).fetchone()
verb = "ALTER" if exists else "CREATE"
conn.execute(sql.SQL(verb + " ROLE {} WITH LOGIN PASSWORD {}").format(
    sql.Identifier(APP_ROLE), sql.Literal(app_password)))
if not conn.execute("SELECT 1 FROM pg_database WHERE datname = %s", (APP_DB,)).fetchone():
    conn.execute(sql.SQL("CREATE DATABASE {} OWNER {} ENCODING 'UTF8' TEMPLATE template0").format(...))
```

- It makes a **separate database user** (`literetailer_app`) that owns only our database. The app never uses the
  `postgres` admin account, and the admin password is **not saved anywhere**.
- `CREATE` if missing, `ALTER` if it exists. That's what lets **reinstalling work** (it was the "database already
  exists" issue we fixed).
- `sql.Identifier` / `sql.Literal` quote names and the password safely.

**2. Random secrets, generated once.** `secrets.token_urlsafe(...)` makes the database password and JWT keys.
They're unique per shop, and kept on upgrade (`old.get("SECRET_KEY") or ...`). Otherwise every upgrade would log
everyone out and lock the app out of its own database.

**3. `_write_env`** fills `backend.env.template` in this order: template → build-time secrets → **values the
client already had** → new values. The shop's own edits survive upgrades.

**4. `seed` runs in a new process.** The settings were loaded when Python started, before `backend.env` existed.
A fresh process reads the new file.

### 6.2 `seed`: tables and first data

```python
def _migrate_and_seed(store_name):
    app = create_app("production")
    with app.app_context():
        upgrade(directory=str(bundle_dir() / "migrations"))   # create / update every table
        if db.session.query(User).count():
            print("Users already exist - first data not added again.")
            return                                          # upgrade: don't touch the shop's data
        # empty database: store "My Store", counters C01-C05, admin / admin123
```

`upgrade` is the same as `flask db upgrade`, which applies the migration files in order. On a new database it
builds everything; on an old one it only adds what's new. That's why **the same command serves both new installs
and upgrades**.

### 6.3 `serve`

```python
def cmd_serve(args):
    from waitress import serve
    app = create_app("production")
    serve(app, host="0.0.0.0", port=5000, threads=16)
```

Waitress is a production web server for Windows (Flask's own server is for development only). `0.0.0.0` means
"accept connections from other PCs", which the counters need.

---

## Part 7 — The Windows service: `frontend\build\winsw\LiteRetailerServer.xml`

A normal exe stops when you log out. A **service** starts with Windows, before anyone logs in, and restarts if it
crashes. WinSW turns our exe into one using this XML:

```xml
<service>
  <id>LiteRetailerServer</id>                              <!-- name for sc.exe -->
  <name>LiteRetail Server</name>                           <!-- name in services.msc -->
  <executable>%BASE%\..\literetailer-backend.exe</executable>   <!-- %BASE% = WinSW's folder -->
  <arguments>serve</arguments>
  <startmode>Automatic</startmode>
  <delayedAutoStart>true</delayedAutoStart>                <!-- start after PostgreSQL is up -->
  <onfailure action="restart" delay="10 sec"/>             <!-- crashed? restart -->
  <logpath>%ProgramData%\LiteRetailer\logs</logpath>
  <log mode="roll-by-size">...</log>                       <!-- logs don't grow for ever -->
</service>
```

---

## Part 8 — Mistakes we hit, and the rule each one taught

| What went wrong | Rule |
|---|---|
| Reinstall stopped: "database already exists" | Every setup step must be **safe to run twice** (create if missing, otherwise update). |
| Upgrade failed: column `search_key` already exists | Migrations must check before adding (`migration_guards.py`), because client databases can differ. |
| "No module named app.utils.migration_guards" on the client | Don't trust PyInstaller to find everything: **list all modules and check the result at build time**. |
| Test a fresh install only? | Always test **both** a fresh install and an install over the previous version, on a PC that never had the dev tools. |
| PowerShell 5.1 broke quotes in `python -c "..."` | Put any non-trivial check in a `.py` file and run the file. |

---

## Part 9 — Recipe: the same installer for another app

### 9.1 Tools to install once on the build PC

- Python 3.13 (`py` launcher) and Node.js LTS
- Nothing else: electron-builder brings NSIS with it, and the script downloads PostgreSQL and WinSW.

### 9.2 Files to copy from this project

| Copy | Change |
|---|---|
| `scripts\build\build_installer.ps1` | folder names, exe name, PostgreSQL version, final file name |
| `scripts\build\check_frozen_backend.py` | spec name folder (`build\<name>`) |
| `backend\<name>.spec` | `datas` (your migrations, templates, assets), `collect_all` list, name, icon |
| `backend\<name>_backend.py` | `APP_DB`, `APP_ROLE`, the first data in `_migrate_and_seed`, default admin |
| `backend\app\utils\paths.py` | `APP_NAME` (folder under ProgramData) |
| `backend\backend.env.template` | your app's settings |
| `frontend\electron-builder.yml` | `appId` (**new unique ID!**), `productName`, `artifactName`, paths |
| `frontend\build\installer.nsh` | `SERVICE_NAME`, `FIREWALL_RULE`, `APP_PORT`, `PG_INSTALLER`, page texts, tasks |
| `frontend\build\winsw\<Service>.xml` | id, name, exe name |
| `frontend\build\icon.ico` | your icon (256×256 inside) |

**Rename everywhere together:** the WinSW exe name (in the build script and `electron-builder.yml`), the XML file
name, `<id>` in the XML, and `SERVICE_NAME` in `installer.nsh` must all be the same word.

### 9.3 Step by step

1. **Make the backend runnable as one program.** Write `<name>_backend.py` with at least `serve`, `setup`,
   `seed`. Test them in development first:
   ```powershell
   python <name>_backend.py setup --host localhost --port 5432 --superuser postgres --superpassword XXX
   python <name>_backend.py serve
   ```
2. **Keep runtime files out of Program Files.** Use a `paths.py` like ours: settings, logs, uploads and backups
   in `C:\ProgramData\<App>`.
3. **Freeze it.** Write the `.spec`, run `pyinstaller <name>.spec --noconfirm`, then run
   `dist\<name>\<name>.exe --help` **and** `setup` **and** `serve` from that folder. Fix every "No module named"
   by adding to `hiddenimports` or `collect_all`.
4. **Configure electron-builder.** Put the frozen folder and WinSW in `extraResources`, set `perMachine: true`,
   and `include: build/installer.nsh`.
5. **Write installer.nsh.** Start from ours. Keep the structure (detect → pages → `customInstall` calling your
   exe → service → firewall), and change names and texts.
6. **Run the build script.**
7. **Test on clean PCs (a virtual machine is ideal: VirtualBox / Hyper-V, with snapshots):**
   - no PostgreSQL → install as Main PC → app opens, log in;
   - PostgreSQL already installed → wrong password is refused on the page → right one works;
   - install the **same** installer again over it (repair);
   - install the **next** version over the old one with real data in it (upgrade);
   - Counter PC on a second machine → reaches the Main PC;
   - restart the PC → service comes up by itself;
   - uninstall → database and ProgramData are still there.

### 9.4 If the other app is not Python + Electron

The method stays the same; only the "freeze" step changes:

| Backend | Turn it into an exe with |
|---|---|
| Python | PyInstaller (this guide) |
| Node.js | `pkg` or Node's single-executable apps |
| Java | jpackage (bundles a Java runtime) |
| .NET | `dotnet publish -r win-x64 --self-contained` |
| Go / Rust | already a single exe |

If there's no Electron front end (for example a web app opened in the browser), use **NSIS on its own** or
**Inno Setup**. The same `installer.nsh` ideas apply; only the electron-builder hooks (`customInstall` etc.)
become NSIS's own `Section` blocks.

### 9.5 Where to look when something fails on a client PC

| Symptom | Look at |
|---|---|
| Installer error during "Creating the database" | `C:\ProgramData\<App>\logs\setup.log` |
| App says "cannot reach server" | `services.msc` → is the service running? then `logs\backend.log` and the WinSW logs in `logs\` |
| Silent update problems | `logs\update.log` |
| Counter can't connect | firewall rule present? `ping <Main PC IP>`, open `http://<IP>:5000/api/v1/health` in a browser |
