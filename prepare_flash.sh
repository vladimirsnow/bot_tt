#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_DIR"

# Runtime-only artifacts: remove before copying to USB.
rm -rf .venv
rm -rf __pycache__
find . -type d -name '__pycache__' -prune -exec rm -rf {} +
find . -type f -name '*.pyc' -delete
find . -type f -name '*.pyo' -delete
find . -type f -name '*.log' -delete

if [[ -d downloads ]]; then
  find downloads -mindepth 1 -delete
else
  mkdir -p downloads
fi

echo 'Project is cleaned for USB transfer.'
echo 'Next on another PC: run ./bootstrap.sh (Linux) or .\\bootstrap.ps1 (Windows).'
