#!/usr/bin/env bash
# One-time setup for ClipForge (bash / macOS / Linux).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"

echo "==> Creating Python venv"
python3 -m venv "$ROOT/backend/.venv"
"$ROOT/backend/.venv/bin/python" -m pip install --upgrade pip
"$ROOT/backend/.venv/bin/python" -m pip install -r "$ROOT/backend/requirements.txt"

echo "==> Installing frontend packages"
(cd "$ROOT/frontend" && npm install)

echo ""
echo "Done. Start with:"
echo "  $ROOT/scripts/run-backend.sh"
echo "  $ROOT/scripts/run-frontend.sh"