# Idempotent deploy for Windows: installs renew_consent.py and registers a
# Task Scheduler task that runs it every 48h10m. Run from a clone
# (.\deploy.ps1) or piped:
#   irm <raw-base>/deploy.ps1 | iex
$ErrorActionPreference = 'Stop'

$RawBase = if ($env:DSNET_RAW_BASE) { $env:DSNET_RAW_BASE }
           else { 'https://raw.githubusercontent.com/almostlight/yes-please-collect-my-mail-for-me/main' }
$InstallDir = if ($env:DSNET_INSTALL_DIR) { $env:DSNET_INSTALL_DIR }
              else { Join-Path $env:LOCALAPPDATA 'dsnet-consent\app' }

$scriptPath = if ($MyInvocation.MyCommand) { $MyInvocation.MyCommand.Path } else { $null }
if ($scriptPath -and (Test-Path (Join-Path (Split-Path -Parent $scriptPath) 'renew_consent.py'))) {
    $AppDir = Split-Path -Parent $scriptPath
    $CredHint = ".\setup_credentials.ps1"
} else {
    $AppDir = $InstallDir
    $CredHint = "irm $RawBase/setup_credentials.ps1 | iex"
    New-Item -ItemType Directory -Force -Path $AppDir | Out-Null
    Invoke-RestMethod "$RawBase/renew_consent.py" -OutFile (Join-Path $AppDir 'renew_consent.py')
}

$ConfigDir = Join-Path $env:APPDATA 'dsnet-consent'
$StateDir = Join-Path $env:LOCALAPPDATA 'dsnet-consent'
New-Item -ItemType Directory -Force -Path $ConfigDir, $StateDir | Out-Null

$Python = (Get-Command python -ErrorAction SilentlyContinue).Source
if ($Python) {
    $Exe = Join-Path (Split-Path -Parent $Python) 'pythonw.exe'
    if (-not (Test-Path $Exe)) { $Exe = $Python }
    $Arg = '"{0}\renew_consent.py" --if-due' -f $AppDir
} else {
    $Exe = 'py'
    $Arg = '-3w "{0}\renew_consent.py" --if-due' -f $AppDir
}

$Action = New-ScheduledTaskAction -Execute $Exe -Argument $Arg
$Trigger = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(5) `
    -RepetitionInterval (New-TimeSpan -Hours 48 -Minutes 10) `
    -RepetitionDuration ([TimeSpan]::MaxValue)
$Settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries -ExecutionTimeLimit (New-TimeSpan -Minutes 10)

Register-ScheduledTask -TaskName 'DSNet-Consent-Renewal' -Action $Action -Trigger $Trigger `
    -Settings $Settings -Description 'Renews DSNet accommodation consent every 48h10m' -Force

Get-ScheduledTask -TaskName 'DSNet-Consent-Renewal' | Select-Object State
Get-ScheduledTaskInfo -TaskName 'DSNet-Consent-Renewal' | Select-Object NextRunTime, LastRunTime

if (-not (Test-Path (Join-Path $ConfigDir 'credentials.env'))) {
    Write-Host "credentials not configured yet: $CredHint"
}
Write-Host "app:  $AppDir\renew_consent.py"
Write-Host "logs: $StateDir\renew_consent.log"
