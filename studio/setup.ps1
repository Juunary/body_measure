# One-time setup. From body-measure\studio:  .\setup.ps1
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
$env:PYTHONUTF8 = "1"

if (-not (Test-Path ..\qr-configurator\backend)) {
  git -C .. submodule update --init --recursive
}
if (-not (Test-Path ..\polo-line-sim\polo_line)) {
  throw "Missing polo-line-sim. Clone the complete body_measure repository."
}

if (-not (Test-Path .venv)) { py -3.12 -m venv .venv }
& .\.venv\Scripts\python -m pip install --quiet --upgrade pip
& .\.venv\Scripts\python -m pip install --quiet -r requirements.txt

# three.js r171 is already in qr-configurator's built DPP viewer; reuse it.
New-Item -ItemType Directory -Force static\vendor | Out-Null
$three = Get-ChildItem ..\qr-configurator\backend\static\dppview\assets\three.module-*.js | Select-Object -First 1
if (-not $three) { throw "The qr-configurator submodule has no Three.js bundle." }
Copy-Item $three.FullName static\vendor\three.module.js -Force

# OrbitControls is not in that bundle; fetch it once for the same release.
if (-not (Test-Path static\vendor\OrbitControls.js)) {
  Invoke-WebRequest "https://cdn.jsdelivr.net/npm/three@0.171.0/examples/jsm/controls/OrbitControls.js" -OutFile static\vendor\OrbitControls.js
}
Write-Host "ready — run .\run.ps1"
