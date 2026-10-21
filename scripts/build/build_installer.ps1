# Builds the LiteRetail client installer: frozen backend + Electron app + PostgreSQL, one .exe.
#
#   powershell -ExecutionPolicy Bypass -File scripts\build\build_installer.ps1 [-RequireSigning]
#
# Output: frontend\release\LiteRetail-Setup-<version>.exe
# One-time downloads (not in git, see .gitignore) are fetched automatically into frontend\build\vendor.
#
# Code signing (documentation\code-signing.md): set ONE of these before running, otherwise the build is unsigned.
#   .pfx certificate:        CSC_LINK=<path to .pfx>  CSC_KEY_PASSWORD=<password>
#   USB token / cert store:  LITERETAIL_SIGN_SUBJECT=<certificate subject name> (token plugged in)
#   Azure Trusted Signing:   AZURE_TENANT_ID, AZURE_CLIENT_ID, AZURE_CLIENT_SECRET,
#                            LITERETAIL_SIGN_ENDPOINT, LITERETAIL_SIGN_ACCOUNT, LITERETAIL_SIGN_PROFILE,
#                            LITERETAIL_SIGN_PUBLISHER (the certificate's subject CN, e.g. LiteCode Software Pvt Ltd)
# -RequireSigning stops the build when neither is set (use it for releases).
param([switch]$RequireSigning)
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

# electron-builder signs the app, the installer, and every .exe it packs (frozen backend, WinSW service).
$signArgs = @()
if ($env:CSC_LINK) {
    if (-not (Test-Path $env:CSC_LINK)) { throw "CSC_LINK points to a missing file: $env:CSC_LINK" }
    $signing = "certificate $env:CSC_LINK"
} elseif ($env:LITERETAIL_SIGN_SUBJECT) {
    $signArgs = @("-c.win.signtoolOptions.certificateSubjectName=$env:LITERETAIL_SIGN_SUBJECT")
    $signing = "certificate store / token: $env:LITERETAIL_SIGN_SUBJECT"
} elseif ($env:LITERETAIL_SIGN_ENDPOINT) {
    foreach ($v in 'AZURE_TENANT_ID', 'AZURE_CLIENT_ID', 'AZURE_CLIENT_SECRET', 'LITERETAIL_SIGN_ACCOUNT',
                   'LITERETAIL_SIGN_PROFILE', 'LITERETAIL_SIGN_PUBLISHER') {
        if (-not [Environment]::GetEnvironmentVariable($v)) { throw "Azure Trusted Signing needs $v" }
    }
    $signArgs = @(
        "-c.win.azureSignOptions.endpoint=$env:LITERETAIL_SIGN_ENDPOINT",
        "-c.win.azureSignOptions.codeSigningAccountName=$env:LITERETAIL_SIGN_ACCOUNT",
        "-c.win.azureSignOptions.certificateProfileName=$env:LITERETAIL_SIGN_PROFILE",
        "-c.win.azureSignOptions.publisherName=$env:LITERETAIL_SIGN_PUBLISHER"
    )
    $signing = "Azure Trusted Signing ($env:LITERETAIL_SIGN_ACCOUNT / $env:LITERETAIL_SIGN_PROFILE)"
} elseif ($RequireSigning) {
    throw 'No code signing configured (see documentation\code-signing.md). Remove -RequireSigning for a test build.'
} else {
    $signing = $null
    Write-Warning 'UNSIGNED build: Windows SmartScreen will warn when the installer runs. Fine for testing only.'
}
if ($signing) { Write-Host "Code signing: $signing" }

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
    npm run dist -- @signArgs
    if ($LASTEXITCODE) { throw 'electron-builder failed' }
} finally { Pop-Location }

$version = (Get-Content (Join-Path $frontend 'package.json') -Raw | ConvertFrom-Json).version
$setup = Get-Item (Join-Path $frontend "release\LiteRetail-Setup-$version.exe")
if ($signing) {
    foreach ($file in @($setup.FullName,
                        (Join-Path $frontend 'release\win-unpacked\LiteRetail.exe'),
                        (Join-Path $frontend 'release\win-unpacked\resources\backend\literetailer-backend.exe'))) {
        $sig = Get-AuthenticodeSignature $file
        if ($sig.Status -ne 'Valid') { throw "Not validly signed ($($sig.Status)): $file" }
        Write-Host "   signed: $(Split-Path $file -Leaf) - $($sig.SignerCertificate.Subject)"
    }
}
Write-Host ("Done: {0} ({1:N0} MB)" -f $setup.FullName, ($setup.Length / 1MB))
