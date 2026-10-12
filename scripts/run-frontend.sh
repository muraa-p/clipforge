#!/usr/bin/env bash
# Start the ClipForge frontend (Next.js) on http://localhost:3000
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT/frontend"
exec npm run dev