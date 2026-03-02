#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_DIR"

if [[ ! -f .env ]]; then
  if [[ ! -f .env.example ]]; then
    echo "Missing .env and .env.example"
    exit 1
  fi
  cp .env.example .env
fi

if grep -Eq '^AUTO_START[[:space:]]*=' .env; then
  sed -i -E 's/^AUTO_START[[:space:]]*=.*/AUTO_START=true/' .env
else
  printf '\nAUTO_START=true\n' >> .env
fi

if ! ./bootstrap.sh >/dev/null 2>&1; then
  echo "Bootstrap failed. Run ./bootstrap.sh manually to see details."
  exit 1
fi

if command -v systemctl >/dev/null 2>&1; then
  if systemctl --user restart tiktok-bot.service >/dev/null 2>&1; then
    echo "Bot started in background via systemd user service."
    exit 0
  fi
fi

if [[ ! -x "$PROJECT_DIR/.venv/bin/python" ]]; then
  echo "Python environment not found: $PROJECT_DIR/.venv/bin/python"
  exit 1
fi

if pgrep -f "$PROJECT_DIR/.venv/bin/python.*$PROJECT_DIR/bot.py" >/dev/null 2>&1; then
  echo "Bot is already running in background."
  exit 0
fi

nohup "$PROJECT_DIR/.venv/bin/python" "$PROJECT_DIR/bot.py" >/dev/null 2>&1 &
disown || true

echo "Bot started in background via nohup."
