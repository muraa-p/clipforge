# Expose ClipForge from anywhere using Tailscale (free for personal use).
#
# 1. Install Tailscale:  https://tailscale.com/download
# 2. Log in on your PC and on your phone/laptop (same tailnet).
# 3. Run this script. It serves port 8000 to your tailnet.
#
# Access from any device on your tailnet at the URL it prints
# (https://<machine>.<tailnet>.ts.net/...).
# The default `serve` keeps it private to your tailnet — the safest option.

$ErrorActionPreference = "Stop"

$Port = if ($env:CLIPFORGE_PORT) { $env:CLIPFORGE_PORT } else { "8000" }

if (-not (Get-Command tailscale -ErrorAction SilentlyContinue)) {
    Write-Host "Tailscale is not installed. Get it from https://tailscale.com/download" -ForegroundColor Yellow
    exit 1
}

Write-Host "==> Serving http://127.0.0.1:$Port on your tailnet"
Write-Host "    (private to your own devices)"
tailscale serve --bg $Port

Write-Host ""
Write-Host "To make it PUBLIC instead (anyone with the link), run:"
Write-Host "    tailscale funnel $Port"
Write-Host ""
Write-Host "Stop serving with:  tailscale serve reset"