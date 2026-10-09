# Registers the "POS Daily Collection" task in Windows Task Scheduler (run once on the server PC, as admin).
#
# Every 15 minutes it runs `flask send-daily-collection`. The command does nothing until the send time set
# in Admin > Settings has passed, then sends each store's collection summary on WhatsApp once; failed sends
# are retried on the next runs (3 tries). Set the WHATSAPP_* values in backend\.env first.
#
#   powershell -ExecutionPolicy Bypass -File scripts\setup\register_daily_report_task.ps1
#   powershell -ExecutionPolicy Bypass -File scripts\setup\register_daily_report_task.ps1 -Remove
param(
    [string]$TaskName = "POS Daily Collection",
    [int]$EveryMinutes = 15,
    [switch]$Remove
)

$ErrorActionPreference = "Stop"

if ($Remove) {
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
    Write-Host "Removed task '$TaskName'."
    return
}

$backend = (Resolve-Path (Join-Path $PSScriptRoot "..\..\backend")).Path
$flask = Join-Path $backend ".venv\Scripts\flask.exe"
if (-not (Test-Path $flask)) { throw "Not found: $flask. Create the backend virtualenv first." }
$logDir = Join-Path $backend "logs"
New-Item -ItemType Directory -Force $logDir | Out-Null

# cmd /c so the output is appended to a log file; the working directory lets flask find .flaskenv and .env.
$action = New-ScheduledTaskAction -Execute "cmd.exe" `
    -Argument "/c `"`"$flask`" send-daily-collection >> `"$logDir\daily_report.log`" 2>&1`"" `
    -WorkingDirectory $backend
$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date).Date `
    -RepetitionInterval (New-TimeSpan -Minutes $EveryMinutes) -RepetitionDuration (New-TimeSpan -Days 3650)
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -MultipleInstances IgnoreNew `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 10)
# SYSTEM: runs whether or not anyone is signed in.
$principal = New-ScheduledTaskPrincipal -UserId "SYSTEM" -LogonType ServiceAccount -RunLevel Highest

Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Settings $settings `
    -Principal $principal -Force | Out-Null
Write-Host "Registered '$TaskName' (every $EveryMinutes min). Log: $logDir\daily_report.log"
