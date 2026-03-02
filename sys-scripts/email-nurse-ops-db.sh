#!/bin/zsh

# email-nurse-ops-db.sh
# Wrapper for: email-nurse ops db-hygiene
# Runs daily to prune old database records and vacuum.

set -o pipefail

INSTALL_DIR="$HOME/.local/share/email-nurse/current"
CONFIG_DIR="$HOME/.config/email-nurse"
LOG_DIR="$HOME/Library/Logs"

ERROR_LOG="${LOG_DIR}/email-nurse-error.log"

log() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') [ops:db] $1"
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

log "Starting db-hygiene"

if "$INSTALL_DIR/venv/bin/email-nurse" ops db-hygiene -v; then
    log "SUCCESS"
else
    EXIT_CODE=$?
    log "FAILED - Exit code: $EXIT_CODE"
    exit $EXIT_CODE
fi
