#!/bin/zsh

# email-nurse-digest.sh - Daily digest report sender

set -o pipefail

INSTALL_DIR="$HOME/.local/share/email-nurse/current"
CONFIG_DIR="$HOME/.config/email-nurse"
LOG_DIR="$HOME/Library/Logs"

log() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') - $1"
}

log "Starting daily digest"

if ! pgrep -xq "Mail"; then
    log "Mail.app not running, skipping digest"
    exit 0
fi

# Load config from .env
if [[ -f "$CONFIG_DIR/.env" ]]; then
    while IFS= read -r line; do
        [[ "$line" =~ ^[[:space:]]*# ]] && continue
        [[ -z "$line" ]] && continue
        export "$line"
    done < "$CONFIG_DIR/.env"
fi

if [[ ! -d "$INSTALL_DIR/venv" ]]; then
    log "ERROR: Installation not found at $INSTALL_DIR"
    exit 1
fi

if "$INSTALL_DIR/venv/bin/email-nurse" autopilot report; then
    log "SUCCESS - Digest sent"
else
    EXIT_CODE=$?
    log "FAILED - Exit code: $EXIT_CODE"
    exit $EXIT_CODE
fi
