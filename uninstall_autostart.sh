#!/usr/bin/env bash
set -euo pipefail

systemctl --user disable --now tiktok-bot.service || true
rm -f "$HOME/.config/systemd/user/tiktok-bot.service"
systemctl --user daemon-reload

echo "Autostart removed"
