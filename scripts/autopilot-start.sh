#!/bin/bash
# Start the email-nurse autopilot scheduled job

launchctl load ~/Library/LaunchAgents/com.bss.email-nurse.plist 2>/dev/null

echo "Autopilot started (runs every 5 minutes)"
