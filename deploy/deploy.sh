#!/usr/bin/env bash
set -euo pipefail

APP_DIR="/opt/trackwiththem"
VENV_DIR="$APP_DIR/venv"
SERVICE_NAME="parcelmate"

echo "=== TrackWithThem Deploy ==="

cd "$APP_DIR"

echo "Pulling latest code..."
git pull origin main

echo "Updating dependencies..."
"$VENV_DIR/bin/pip" install -r requirements.txt --quiet

echo "Running database migrations..."
"$VENV_DIR/bin/alembic" upgrade head

echo "Restarting service..."
sudo systemctl restart "$SERVICE_NAME"

echo "=== Deploy complete ==="
echo "Check status with: systemctl status $SERVICE_NAME"
echo "Check logs with: journalctl -u $SERVICE_NAME -f"
