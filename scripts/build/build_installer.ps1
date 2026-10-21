# Builds the LiteRetail client installer: frozen backend + Electron app + PostgreSQL, one .exe.
#
#   powershell -ExecutionPolicy Bypass -File scripts\build\build_installer.ps1
#
# Output: frontend\release\LiteRetail-Setup-<version>.exe
# One-time downloads (not in git, see .gitignore) are fetched automatically into frontend\build\vendor.
$ErrorActionPreference = 'Stop'

$root     = Resolve-Path (Join-Path $PSScriptRoot '..\..')
$backend  = Join-Path $root 'backend'
$frontend = Join-Path $root 'frontend'
$vendor   = Join-Path $frontend 'build\vendor'

# Keep in step with PG_INSTALLER in frontend\build\installer.nsh.
$pgFile = 'postgresql-17.6-1-windows-x64.exe'
$pgUrl  = "https://get.enterprisedb.com/postgresql/$pgFile"
$winswUrl = 'https://github.com/winsw/winsw/releases/download/v2.12.0/WinSW-x64.exe'

function Get-Once($url, $path) {
    if (Test-Path $path) { return }
    New-Item -ItemType Directory -Force (Split-Path $path) | Out-Null
    Write-Host "Downloading $url"
    Invoke-WebRequest -Uri $url -OutFile "$path.part" -UseBasicParsing
    Move-Item "$path.part" $path
}

Write-Host '== 1/3 Third-party installers'
Get-Once $pgUrl    (Join-Path $vendor "postgresql\$pgFile")
Get-Once $winswUrl (Join-Path $vendor 'winsw\LiteRetailerServer.exe')

Write-Host '== 2/3 Backend -> backend\dist\literetailer-backend'
Write-Host '   (PyInstaller prints little and takes 3-5 minutes; the psycopg_binary warning is harmless)'
Push-Location $backend
try {
    if (-not (Test-Path '.venv\Scripts\python.exe')) { py -3.13 -m venv .venv }
    & .venv\Scripts\python.exe -m pip install -q -r requirements.txt -r requirements-build.txt
    if ($LASTEXITCODE) { throw 'pip install failed' }
    & .venv\Scripts\pyinstaller.exe literetailer-backend.spec --noconfirm --log-level WARN
    if ($LASTEXITCODE) { throw 'PyInstaller failed' }
    & dist\literetailer-backend\literetailer-backend.exe --help | Out-Null
    if ($LASTEXITCODE) { throw 'Frozen backend does not start' }
} finally { Pop-Location }

Write-Host '== 3/3 App + installer -> frontend\release'
Push-Location $frontend
try {
    npm ci
    if ($LASTEXITCODE) { throw 'npm ci failed' }
    # Electron downloads its program in an install step that can fail quietly ("Error: Electron uninstall"
    # on npm run dev afterwards); repair it here.
    if (-not (Test-Path 'node_modules\electron\path.txt')) {
        Write-Host '   Electron binary missing - downloading it again'
        node node_modules\electron\install.js
        if ($LASTEXITCODE -or -not (Test-Path 'node_modules\electron\path.txt')) { throw 'Electron install failed' }
    }
    npm run typecheck
    if ($LASTEXITCODE) { throw 'typecheck failed' }
    npm run dist
    if ($LASTEXITCODE) { throw 'electron-builder failed' }
} finally { Pop-Location }

Get-ChildItem (Join-Path $frontend 'release\LiteRetail-Setup-*.exe') | ForEach-Object {
    Write-Host ("Done: {0} ({1:N0} MB)" -f $_.FullName, ($_.Length / 1MB))
}
