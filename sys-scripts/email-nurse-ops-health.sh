#!/bin/zsh

# email-nurse-ops-health.sh
# Wrapper for: email-nurse ops process-health
# Runs on a schedule to detect silent autopilot and restart if needed.

set -o pipefail

INSTALL_DIR="$HOME/.local/share/email-nurse/current"
CONFIG_DIR="$HOME/.config/email-nurse"
LOG_DIR="$HOME/Library/Logs"

ERROR_LOG="${LOG_DIR}/email-nurse-error.log"

log() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') [ops:health] $1"
}

# Load non-sensitive config from .env
if [[ -f "$CONFIG_DIR/.env" ]]; then
    while IFS= read -r line; do
        [[ "$line" =~ ^[[:space:]]*# ]] && continue
        [[ -z "$line" ]] && continue
        [[ "$line" =~ .*API_KEY.* ]] && continue
        export "$line"
    done < "$CONFIG_DIR/.env"
fi

# Verify installation
if [[ ! -d "$INSTALL_DIR/venv" ]]; then
    log "ERROR: Installation not found at $INSTALL_DIR" >> "$ERROR_LOG"
    exit 1
fi

log "Starting process-health check"

if "$INSTALL_DIR/venv/bin/email-nurse" ops process-health -v; then
    log "SUCCESS"
else
    EXIT_CODE=$?
    log "FAILED - Exit code: $EXIT_CODE"
    exit $EXIT_CODE
fi
