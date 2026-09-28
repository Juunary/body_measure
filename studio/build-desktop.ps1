param([switch]$SkipInstaller)
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
$env:PYTHONUTF8 = "1"

if (-not (Test-Path static\vendor\three.module.js)) {
  throw "static/vendor/three.module.js is missing. Run setup.ps1 first."
}
if (-not (Test-Path .venv-desktop)) { py -3.12 -m venv .venv-desktop }
& .\.venv-desktop\Scripts\python -m pip install --quiet --upgrade pip
if ($LASTEXITCODE) { throw "pip upgrade failed with exit code $LASTEXITCODE" }
& .\.venv-desktop\Scripts\python -m pip install --quiet -r requirements-desktop.txt
if ($LASTEXITCODE) { throw "desktop dependency installation failed with exit code $LASTEXITCODE" }
& .\.venv-desktop\Scripts\pyinstaller.exe --noconfirm --clean polo-simulator.spec
if ($LASTEXITCODE) { throw "PyInstaller failed with exit code $LASTEXITCODE. Close a running PoloSimulator and retry." }

$exe = Resolve-Path dist\PoloSimulator\PoloSimulator.exe
Write-Host "Desktop bundle: $exe"
if ($SkipInstaller) { exit 0 }

$deps = Join-Path $PSScriptRoot "installer\deps"
New-Item -ItemType Directory -Force $deps | Out-Null
$webViewInstaller = Join-Path $deps "MicrosoftEdgeWebView2RuntimeInstallerX64.exe"
if (-not (Test-Path $webViewInstaller)) {
  Write-Host "Downloading Microsoft's signed WebView2 Evergreen standalone installer..."
  Invoke-WebRequest "https://go.microsoft.com/fwlink/?linkid=2124701" -OutFile $webViewInstaller
}
$signature = Get-AuthenticodeSignature -LiteralPath $webViewInstaller
if ($signature.Status -ne "Valid" -or $signature.SignerCertificate.Subject -notmatch "Microsoft") {
  throw "WebView2 installer signature is not a valid Microsoft signature."
}

$iscc = @(
  "$env:LOCALAPPDATA\Programs\Inno Setup 7\ISCC.exe", "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe",
  "$env:ProgramFiles\Inno Setup 7\ISCC.exe", "${env:ProgramFiles(x86)}\Inno Setup 7\ISCC.exe",
  "$env:ProgramFiles\Inno Setup 6\ISCC.exe", "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe"
) | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
if (-not $iscc) {
  throw "The verified onedir bundle was built, but Inno Setup 6 or 7 is required to create Setup.exe."
}
& $iscc installer\polo-simulator.iss
if ($LASTEXITCODE) { throw "Inno Setup failed with exit code $LASTEXITCODE" }
Write-Host "Installer: $PSScriptRoot\installer\output\PoloSimulatorSetup.exe"
