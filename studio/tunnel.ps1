# Open the studio on a public https link from this machine, with a password.
#
#   .\tunnel.ps1 -Password "..."            English page
#   .\tunnel.ps1 -Password "..." -Lang KR   Korean page
#
# Two processes: the studio on 127.0.0.1:8010 with STUDIO_PASSWORD set, and a
# Cloudflare quick tunnel that prints a random https://….trycloudflare.com
# link. The link lives as long as this window does; the data never leaves
# this machine except as the page shows it, and the password is asked once
# per browser. cloudflared:  winget install --id Cloudflare.cloudflared
param(
  [Parameter(Mandatory = $true)][string]$Password,
  [string]$Lang = "EN"
)
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

if (-not (Get-Command cloudflared -ErrorAction SilentlyContinue)) {
  Write-Host "cloudflared is not installed. Install it and run again:" -ForegroundColor Yellow
  Write-Host "  winget install --id Cloudflare.cloudflared"
  exit 1
}

# A studio already listening on 8010 (run.ps1, or a tunnel in another
# window) would answer the health check below with ITS password, and this
# window's server would fail to bind — the tunnel would then front the
# other server. Refuse instead of guessing whose it is.
$held = Get-NetTCPConnection -LocalPort 8010 -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
if ($held) {
  $owner = Get-Process -Id $held.OwningProcess -ErrorAction SilentlyContinue
  Write-Host "port 8010 is already in use (pid $($held.OwningProcess), $($owner.ProcessName)). Stop that studio first:" -ForegroundColor Yellow
  Write-Host "  Stop-Process -Id $($held.OwningProcess)"
  exit 1
}

$env:PYTHONUTF8 = "1"
$env:STUDIO_PASSWORD = $Password
$env:STUDIO_LANG = switch ($Lang.ToUpper()) { "KR" { "ko" } "KO" { "ko" } "DE" { "de" } default { "en" } }

$server = Start-Process -FilePath ".\.venv\Scripts\python.exe" `
  -ArgumentList "-m", "uvicorn", "studio.server:app", "--host", "127.0.0.1", "--port", "8010" `
  -PassThru -NoNewWindow
try {
  $ready = $false
  for ($i = 0; $i -lt 40 -and -not $ready; $i++) {
    Start-Sleep -Milliseconds 500
    try { $ready = (Invoke-WebRequest -UseBasicParsing http://127.0.0.1:8010/healthz -TimeoutSec 2).StatusCode -eq 200 } catch { }
  }
  if (-not $ready) { throw "the studio did not start on 127.0.0.1:8010" }
  Write-Host "studio up (password protected). Opening the tunnel — the public link appears below." -ForegroundColor Green
  & cloudflared tunnel --url http://127.0.0.1:8010
} finally {
  if ($server -and -not $server.HasExited) { Stop-Process -Id $server.Id -Force }
}
