# One-time setup for ClipForge (PowerShell / Windows).
$ErrorActionPreference = "Stop"

$Root = Join-Path $PSScriptRoot ".." | Resolve-Path
$Backend = Join-Path $Root "backend"
$Frontend = Join-Path $Root "frontend"

Write-Host "==> Creating Python venv"
python -m venv (Join-Path $Backend ".venv")
$Py = Join-Path $Backend ".venv\Scripts\python.exe"
$Pip = Join-Path $Backend ".venv\Scripts\pip.exe"

& $Py -m pip install --upgrade pip
& $Pip install -r (Join-Path $Backend "requirements.txt")

Write-Host "==> Installing frontend packages"
Push-Location $Frontend
npm install
Pop-Location

Write-Host ""
Write-Host "Done. Start with:"
Write-Host "  $Root\scripts\run-backend.ps1"
Write-Host "  $Root\scripts\run-frontend.ps1"
Write-Host "Then open http://localhost:3000"