# Creates the off-repo credentials file for renew_consent.py on Windows.
# Run from a clone (.\setup_credentials.ps1) or piped:
#   irm <raw-base>/setup_credentials.ps1 | iex
# Refuses to overwrite unless -Force is passed. No param() block so it works
# when piped through iex.
$ErrorActionPreference = 'Stop'
$Force = $args -contains '-Force'

$Dest = if ($env:DSNET_CREDENTIALS_FILE) { $env:DSNET_CREDENTIALS_FILE }
        else { Join-Path $env:APPDATA 'dsnet-consent\credentials.env' }
if ((Test-Path $Dest) -and -not $Force) {
    Write-Error "Refusing to overwrite $Dest (pass -Force to replace)."
    exit 1
}

New-Item -ItemType Directory -Force -Path (Split-Path -Parent $Dest) | Out-Null
$email = Read-Host 'DSNet panel e-mail'
$ss = Read-Host -AsSecureString 'DSNet panel password'
$bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($ss)
$password = [Runtime.InteropServices.Marshal]::PtrToStringAuto($bstr)
[Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr)

if (-not $email -or -not $password) { Write-Error 'Empty e-mail or password, aborting.'; exit 1 }

@"
# Credentials for https://panel.dsnet.agh.edu.pl - keep this file OUT of any git repo.
DSNET_EMAIL=$email
DSNET_PASSWORD=$password
"@ | Set-Content -Path $Dest -Encoding utf8 -NoNewline

icacls "$Dest" /inheritance:r /grant:r "$($env:USERNAME):F" | Out-Null
Write-Host "Wrote $Dest (restricted to $env:USERNAME)."
Write-Host 'Next: deploy the 48h10m schedule (.\deploy.ps1 or irm <raw-base>/deploy.ps1 | iex)'
Write-Host 'Test manually: python renew_consent.py --dry-run'
