#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_DIR"

if [[ ! -f .env ]]; then
  echo "[autostart] .env not found -> skip"
  exit 0
fi

AUTO_START_VALUE="$(grep -E '^AUTO_START=' .env | tail -n1 | cut -d= -f2- | tr -d '[:space:]' | tr '[:upper:]' '[:lower:]')"
case "$AUTO_START_VALUE" in
  true|1|yes|on)
    ;;
  *)
    echo "[autostart] AUTO_START is not true -> skip"
    exit 0
    ;;
esac

if [[ ! -x .venv/bin/python ]]; then
  echo "[autostart] .venv/bin/python not found -> skip"
  exit 0
fi

exec "$PROJECT_DIR/.venv/bin/python" "$PROJECT_DIR/bot.py"
