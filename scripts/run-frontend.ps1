# Start the ClipForge frontend (Next.js) on http://localhost:3000
$ErrorActionPreference = "Stop"
$Root = Join-Path $PSScriptRoot ".." | Resolve-Path
Set-Location (Join-Path $Root "frontend")
npm run dev