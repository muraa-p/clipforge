#!/usr/bin/env bash
# Start the ClipForge backend (FastAPI) on http://127.0.0.1:8000
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT/backend"
exec "$ROOT/backend/.venv/bin/python" -m uvicorn app.main:app --host 127.0.0.1 --port 8000