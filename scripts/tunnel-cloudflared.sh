#!/usr/bin/env bash
# Expose ClipForge from anywhere using a FREE Cloudflare quick tunnel.
# No account needed. Gives you a random https://*.trycloudflare.com URL.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BIN="$ROOT/backend/bin"
mkdir -p "$BIN"
EXE="$BIN/cloudflared"

if [ ! -x "$EXE" ]; then
  echo "==> Downloading cloudflared (free)…"
  case "$(uname -s)" in
    Darwin) URL="https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-darwin-amd64.tgz";;
    *)      URL="https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64";;
  esac
  if [[ "$URL" == *.tgz ]]; then
    curl -L "$URL" -o "$BIN/cloudflared.tgz"
    tar -xzf "$BIN/cloudflared.tgz" -C "$BIN"
  else
    curl -L "$URL" -o "$EXE"
  fi
  chmod +x "$EXE"
fi

PORT="${CLIPFORGE_PORT:-8000}"
[ -n "${CLIPFORGE_ACCESS_TOKEN:-}" ] || echo "WARNING: CLIPFORGE_ACCESS_TOKEN not set — set it in both shells before sharing the URL."
exec "$EXE" tunnel --url "http://127.0.0.1:$PORT"