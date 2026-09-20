#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

if [[ ! -d ".venv" ]]; then
  echo "Missing .venv. Run: python3 -m venv .venv"
  exit 1
fi

source .venv/bin/activate
exec uvicorn backend.main:app --host 127.0.0.1 --port "${PORT:-8000}"
