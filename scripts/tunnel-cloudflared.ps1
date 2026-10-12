# Expose ClipForge from anywhere using a FREE Cloudflare quick tunnel.
# No account needed. Gives you a random https://*.trycloudflare.com URL.
#
# Your PC must stay on while you use it. The URL changes each time you run this.
#
# Recommended: set an access token first so only you can use it:
#   $env:CLIPFORGE_ACCESS_TOKEN = "pick-a-long-secret"
#   $env:NEXT_PUBLIC_ACCESS_TOKEN = $env:CLIPFORGE_ACCESS_TOKEN
# (Set the same value in both backend and frontend shells.)

$ErrorActionPreference = "Stop"
$Root = Join-Path $PSScriptRoot ".." | Resolve-Path
$Bin = Join-Path $Root "backend\bin"
New-Item -ItemType Directory -Force -Path $Bin | Out-Null
$Exe = Join-Path $Bin "cloudflared.exe"

if (-not (Test-Path $Exe)) {
    Write-Host "==> Downloading cloudflared (free, ~30 MB)…"
    $Url = "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe"
    Invoke-WebRequest -Uri $Url -OutFile $Exe
    Write-Host "    saved to $Exe"
}

$Port = if ($env:CLIPFORGE_PORT) { $env:CLIPFORGE_PORT } else { "8000" }

if (-not $env:CLIPFORGE_ACCESS_TOKEN) {
    Write-Host ""
    Write-Host "WARNING: CLIPFORGE_ACCESS_TOKEN is not set." -ForegroundColor Yellow
    Write-Host "Anyone with the tunnel URL could use your machine. Set a token in BOTH" -ForegroundColor Yellow
    Write-Host "the backend shell and the frontend shell before sharing the link." -ForegroundColor Yellow
}

Write-Host ""
Write-Host "==> Starting tunnel to http://127.0.0.1:$Port"
Write-Host "    Copy the https://*.trycloudflare.com URL it prints below."
Write-Host ""

& $Exe tunnel --url "http://127.0.0.1:$Port"