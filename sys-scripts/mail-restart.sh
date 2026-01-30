#!/bin/bash
# Restart Mail.app and autopilot service
# Useful for clearing sync issues or refreshing Mail.app state

set -euo pipefail

echo "$(date): Stopping autopilot service..."
launchctl unload ~/Library/LaunchAgents/com.bss.email-nurse.plist 2>/dev/null || true
pkill -f "email-nurse autopilot" 2>/dev/null || true

echo "$(date): Quitting Mail.app..."
osascript -e 'tell application "Mail" to quit' 2>/dev/null || true

echo "$(date): Waiting 5 minutes..."
sleep 300

echo "$(date): Opening Mail.app..."
open -a Mail

echo "$(date): Waiting 1 minute for Mail.app to sync..."
sleep 60

echo "$(date): Starting autopilot service..."
launchctl load ~/Library/LaunchAgents/com.bss.email-nurse.plist

echo "$(date): Mail restart complete"
