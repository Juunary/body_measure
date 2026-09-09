# Start the studio. From body-measure\studio:
#   .\run.ps1        English page
#   .\run.ps1 KR     Korean page   (DE for German)
# then open http://127.0.0.1:8010
param([string]$Lang = "EN")
$env:PYTHONUTF8 = "1"
$env:STUDIO_LANG = switch ($Lang.ToUpper()) { "KR" { "ko" } "KO" { "ko" } "DE" { "de" } default { "en" } }
Set-Location $PSScriptRoot
& .\.venv\Scripts\python -m uvicorn studio.server:app --host 127.0.0.1 --port 8010
