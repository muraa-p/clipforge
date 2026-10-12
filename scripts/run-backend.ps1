# Start the ClipForge backend (FastAPI) on http://127.0.0.1:8000
$ErrorActionPreference = "Stop"
$Root = Join-Path $PSScriptRoot ".." | Resolve-Path
Set-Location (Join-Path $Root "backend")
& (Join-Path $Root "backend\.venv\Scripts\python.exe") -m uvicorn app.main:app --host 127.0.0.1 --port 8000