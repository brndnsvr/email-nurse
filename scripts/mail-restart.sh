#!/bin/bash
# Restart Mail.app and autopilot service
# Runs once every 3 days to clear sync issues and refresh Mail.app state

set -euo pipefail

# Check if we should run (only every 3 days)
TIMESTAMP_FILE="$HOME/.config/email-nurse/last-mail-restart"
CURRENT_TIME=$(date +%s)
RUN_INTERVAL=$((3 * 24 * 60 * 60))  # 3 days in seconds

if [ -f "$TIMESTAMP_FILE" ]; then
    LAST_RUN=$(cat "$TIMESTAMP_FILE")
    TIME_SINCE_LAST=$((CURRENT_TIME - LAST_RUN))

    if [ "$TIME_SINCE_LAST" -lt "$RUN_INTERVAL" ]; then
        HOURS_REMAINING=$(( (RUN_INTERVAL - TIME_SINCE_LAST) / 3600 ))
        echo "$(date): Skipping restart - last run was $(($TIME_SINCE_LAST / 3600)) hours ago (need 72 hours)"
        echo "$(date): Next restart in approximately $HOURS_REMAINING hours"
        exit 0
    fi
fi

echo "$(date): Starting Mail.app restart (last run: $(test -f "$TIMESTAMP_FILE" && echo "$(( (CURRENT_TIME - $(cat "$TIMESTAMP_FILE")) / 3600 )) hours ago" || echo "never"))"

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

# Record successful restart timestamp
mkdir -p "$HOME/.config/email-nurse"
echo "$CURRENT_TIME" > "$TIMESTAMP_FILE"

echo "$(date): Mail restart complete"
