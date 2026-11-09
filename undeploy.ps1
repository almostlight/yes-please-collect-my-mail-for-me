# Idempotent teardown for Windows: removes the Task Scheduler task created
# by deploy.ps1. Credentials and state are kept.
# Pipe-safe: irm <raw-base>/undeploy.ps1 | iex
$ErrorActionPreference = 'Stop'
$TaskName = 'DSNet-Consent-Renewal'

if (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue) {
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
    Write-Host "removed scheduled task $TaskName"
} else {
    Write-Host "scheduled task $TaskName not installed, nothing to do"
}
Write-Host 'credentials/state kept in %APPDATA%\dsnet-consent and %LOCALAPPDATA%\dsnet-consent'
