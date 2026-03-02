#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SERVICE_DIR="$HOME/.config/systemd/user"
SERVICE_FILE="$SERVICE_DIR/tiktok-bot.service"

mkdir -p "$SERVICE_DIR"

cat > "$SERVICE_FILE" <<UNIT
[Unit]
Description=Telegram TikTok Forward Bot
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=$PROJECT_DIR
ExecStart=/usr/bin/env bash -c 'exec "$PROJECT_DIR/autostart_entry.sh"'
Restart=on-failure
RestartSec=5
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=default.target
UNIT

systemctl --user daemon-reload
systemctl --user enable --now tiktok-bot.service
systemctl --user status tiktok-bot.service --no-pager --lines=20 || true

echo
echo "Autostart installed: $SERVICE_FILE"
echo "View logs: journalctl --user -u tiktok-bot.service -f"
echo "If you need start at boot without login: sudo loginctl enable-linger $USER"
