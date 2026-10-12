#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# ClipForge engine — one-command installer for an always-on Linux box.
#
# ClipForge is at https://github.com/muraa-p/clipforge
# Run this ON the machine that will host the engine (free VM, home server, NAS).
# It installs Docker if needed, fetches the source, generates a strong access
# token, and starts the engine in the background with auto-restart.
#
#   curl -fsSL https://raw.githubusercontent.com/muraa-p/clipforge/main/scripts/deploy-engine.sh | bash
#
# Or, if you already cloned the repo, from its root:
#   bash scripts/deploy-engine.sh
#
# Overridable via env:
#   CLIPFORGE_REPO_URL  (used only when the source isn't already present)
#   CLIPFORGE_SUBDIR    subfolder holding docker-compose.yml (default "")
#   CLIPFORGE_DIR       where to put the source        (default ~/clipforge)
#   CLIPFORGE_PORT      host port                      (default 8000)
#   CLIPFORGE_ACCESS_TOKEN  pre-set a token instead of generating one
# ---------------------------------------------------------------------------
set -euo pipefail

REPO_URL="${CLIPFORGE_REPO_URL:-https://github.com/muraa-p/clipforge.git}"
SUBDIR="${CLIPFORGE_SUBDIR:-}"
DEST="${CLIPFORGE_DIR:-$HOME/clipforge}"
PORT="${CLIPFORGE_PORT:-8000}"

say() { printf '\n\033[1;36m==> %s\033[0m\n' "$*"; }
have() { command -v "$1" >/dev/null 2>&1; }
SUDO=""
if [ "$(id -u)" -ne 0 ]; then SUDO="sudo"; fi

say "Checking Docker"
if ! have docker; then
  say "Installing Docker (official convenience script)"
  curl -fsSL https://get.docker.com | $SUDO sh
  $SUDO usermod -aG docker "$(id -un)" || true
fi
DOCKER="$SUDO docker"
if $SUDO docker compose version >/dev/null 2>&1; then
  COMPOSE="$DOCKER compose"
elif have docker-compose; then
  COMPOSE="$SUDO docker-compose"
else
  say "Installing the Docker Compose plugin"
  $SUDO apt-get update -y && $SUDO apt-get install -y docker-compose-plugin
  COMPOSE="$DOCKER compose"
fi

# If we're not already inside a clipforge checkout, clone one.
if [ ! -f "./docker-compose.yml" ] || [ ! -d "./backend/app" ]; then
  say "Fetching source into $DEST"
  if ! have git; then
    $SUDO apt-get update -y && $SUDO apt-get install -y git
  fi
  if [ -d "$DEST/.git" ]; then
    git -C "$DEST" pull --ff-only || true
  else
    rm -rf "$DEST"
    git clone --depth 1 "$REPO_URL" "$DEST"
  fi
  cd "$DEST/${SUBDIR:-.}"
fi

say "Writing .env"
TOKEN="${CLIPFORGE_ACCESS_TOKEN:-}"
if [ -z "$TOKEN" ]; then
  if have openssl; then TOKEN="$(openssl rand -hex 24)"; else TOKEN="$(head -c 32 /dev/urandom | od -An -tx1 | tr -d ' \n')"; fi
fi
cat > .env <<EOF
CLIPFORGE_ACCESS_TOKEN=$TOKEN
CLIPFORGE_PORT=$PORT
CLIPFORGE_MAX_CONCURRENT_JOBS=2
CLIPFORGE_MAX_QUEUED_JOBS=8
CLIPFORGE_DATA_TTL_HOURS=24
EOF

say "Building + starting the engine"
$COMPOSE up -d --build

IP="$(hostname -I 2>/dev/null | awk '{print $1}')"
PUBLIC_IP="$(curl -fsS --max-time 5 https://api.ipify.org 2>/dev/null || echo '<your-public-ip>')"

cat <<EOF

──────────────────────────────────────────────────────────────
✅ ClipForge engine is running.

  Engine URL      : http://$PUBLIC_IP:$PORT      (local: http://$IP:$PORT)
  Access token    : $TOKEN

  Put BOTH of those into the web UI →  ⚙ Settings.

  • Open TCP port $PORT in your cloud firewall / security list.
  • Health check   : http://$PUBLIC_IP:$PORT/api/health
  • Logs           : docker compose logs -f
  • Update         : git pull && docker compose up -d --build
  • Stop           : docker compose down
──────────────────────────────────────────────────────────────
EOF
