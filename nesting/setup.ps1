# One-time setup. From ITA\nesting:  .\setup.ps1
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
$env:PYTHONUTF8 = "1"

if (-not (Test-Path .venv)) { py -3.12 -m venv .venv }
& .\.venv\Scripts\python -m pip install --quiet --upgrade pip
& .\.venv\Scripts\python -m pip install --quiet -r requirements.txt
Write-Host "ready - run: .\.venv\Scripts\python -m nesting import examples\schnittteile-hemd.pdf -o out\pieces.json"
