#!/bin/zsh
# restart.sh - Restart the email-nurse watcher service
#
# Usage: ./scripts/restart.sh
#
# This script safely restarts the email-nurse watcher by:
# 1. Stopping any running watcher process
# 2. Clearing stale PID locks
# 3. Starting the launchd service
# 4. Verifying the watcher is running

set -e

INSTALL_DIR="$HOME/.local/share/email-nurse/current"
SERVICE="com.bss.email-nurse-watcher"

echo "Stopping email-nurse watcher..."
pkill -f 'email-nurse autopilot watch' 2>/dev/null || true
sleep 2

echo "Clearing stale PID lock..."
"$INSTALL_DIR/venv/bin/email-nurse" autopilot reset-watcher 2>/dev/null || true

echo "Starting service..."
launchctl start "$SERVICE"
sleep 3

# Verify
PID=$(pgrep -f 'email-nurse autopilot watch' 2>/dev/null || true)
if [[ -n "$PID" ]]; then
    echo "✓ Watcher running (PID $PID)"
else
    echo "✗ Watcher failed to start - check logs:"
    echo "  tail ~/Library/Logs/email-nurse-watcher-error.log"
    exit 1
fi
