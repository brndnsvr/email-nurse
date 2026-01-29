#!/bin/bash
# Stop the email-nurse autopilot scheduled job

launchctl unload ~/Library/LaunchAgents/com.bss.email-nurse.plist 2>/dev/null
pkill -f "email-nurse autopilot" 2>/dev/null

echo "Autopilot stopped"
