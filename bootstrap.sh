#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_DIR"

if ! command -v python3 >/dev/null 2>&1; then
  echo "python3 is required"
  exit 1
fi

python3 -m venv .venv || true

if [[ ! -x .venv/bin/python ]]; then
  echo "venv python not found"
  exit 1
fi

if [[ ! -x .venv/bin/pip ]]; then
  if ! command -v curl >/dev/null 2>&1; then
    echo "curl is required to bootstrap pip"
    exit 1
  fi
  curl -fsSL https://bootstrap.pypa.io/get-pip.py -o /tmp/get-pip.py
  ./.venv/bin/python /tmp/get-pip.py
fi

./.venv/bin/python -m pip install --upgrade pip
./.venv/bin/pip install -r requirements.txt

if [[ ! -f .env ]]; then
  cp .env.example .env
  echo ".env created from .env.example"
fi

if ! grep -q '^AUTO_START=' .env; then
  printf '\nAUTO_START=false\n' >> .env
fi

AUTO_START_VALUE="$(grep -E '^AUTO_START=' .env | tail -n1 | cut -d= -f2- | tr -d '[:space:]' | tr '[:upper:]' '[:lower:]')"

if [[ "$AUTO_START_VALUE" =~ ^(true|1|yes|on)$ ]]; then
  ./install_autostart.sh
  echo "AUTO_START=true -> Linux autostart enabled"
else
  ./uninstall_autostart.sh || true
  echo "AUTO_START=false -> Linux autostart disabled"
fi

echo
echo "Done. Edit .env (BOT_TOKEN)."
echo "Start bot manually: source .venv/bin/activate && python bot.py"
echo "After changing AUTO_START, rerun: ./bootstrap.sh"
