# Launch both servers in new console windows (Windows only).
$Root = Join-Path $PSScriptRoot ".." | Resolve-Path
Start-Process powershell -ArgumentList "-NoExit", "-Command", "& '$Root\scripts\run-backend.ps1'" -WorkingDirectory $Root
Start-Process powershell -ArgumentList "-NoExit", "-Command", "& '$Root\scripts\run-frontend.ps1'" -WorkingDirectory $Root
Write-Host "Backend → http://127.0.0.1:8000   Frontend → http://localhost:3000"