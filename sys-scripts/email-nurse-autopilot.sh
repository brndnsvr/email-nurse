#!/bin/zsh

# email-nurse-autopilot.sh
# System-installed launcher for email-nurse (repo-independent)
#
# Paths:
#   Install:  ~/.local/share/email-nurse/current/
#   Config:   ~/.config/email-nurse/
#   State:    ~/.local/state/email-nurse/
#   Logs:     ~/Library/Logs/
#   Secrets:  macOS Keychain or .env fallback

# Strict mode
set -o pipefail

# Paths
INSTALL_DIR="$HOME/.local/share/email-nurse/current"
CONFIG_DIR="$HOME/.config/email-nurse"
STATE_DIR="$HOME/.local/state/email-nurse"
LOG_DIR="$HOME/Library/Logs"

# Log files
ERROR_LOG="${LOG_DIR}/email-nurse-error.log"
OUTPUT_LOG="${LOG_DIR}/email-nurse.log"

# State files
RETRY_STATE="${STATE_DIR}/.retry_count"
PLIST_PATH="$HOME/Library/LaunchAgents/com.bss.email-nurse.plist"

# Ensure state directory exists
mkdir -p "$STATE_DIR"

# ─────────────────────────────────────────────────────────────────────
# Skip if Mail.app is not running
# ─────────────────────────────────────────────────────────────────────
if ! pgrep -xq "Mail"; then
    echo "$(date '+%Y-%m-%d %H:%M:%S') - Mail.app not running, skipping"
    exit 0
fi

# ─────────────────────────────────────────────────────────────────────
# Load Secrets from macOS Keychain (with .env fallback)
# ─────────────────────────────────────────────────────────────────────
export ANTHROPIC_API_KEY=$(security find-generic-password -a "$USER" \
    -s "email-nurse-anthropic" -w 2>/dev/null)

# Fallback: load API key from .env if not in Keychain
if [[ -z "$ANTHROPIC_API_KEY" && -f "$CONFIG_DIR/.env" ]]; then
    ANTHROPIC_API_KEY=$(grep -E "^ANTHROPIC_API_KEY=" "$CONFIG_DIR/.env" | cut -d= -f2- | tr -d "'\"")
    export ANTHROPIC_API_KEY
fi

# Optional: OpenAI key if present
OPENAI_KEY=$(security find-generic-password -a "$USER" \
    -s "email-nurse-openai" -w 2>/dev/null)
if [[ -n "$OPENAI_KEY" ]]; then
    export OPENAI_API_KEY="$OPENAI_KEY"
fi

# ─────────────────────────────────────────────────────────────────────
# Load Non-Sensitive Config from .env (if exists)
# ─────────────────────────────────────────────────────────────────────
if [[ -f "$CONFIG_DIR/.env" ]]; then
    # Load all vars EXCEPT API keys (those come from Keychain or above)
    while IFS= read -r line; do
        # Skip comments and empty lines
        [[ "$line" =~ ^[[:space:]]*# ]] && continue
        [[ -z "$line" ]] && continue
        # Skip API keys (already handled above)
        [[ "$line" =~ .*API_KEY.* ]] && continue
        # Export the variable
        export "$line"
    done < "$CONFIG_DIR/.env"
fi

# ─────────────────────────────────────────────────────────────────────
# Verify Installation
# ─────────────────────────────────────────────────────────────────────
if [[ ! -d "$INSTALL_DIR/venv" ]]; then
    echo "$(date '+%Y-%m-%d %H:%M:%S') - ERROR: Installation not found at $INSTALL_DIR" >> "$ERROR_LOG"
    exit 1
fi

if [[ -z "$ANTHROPIC_API_KEY" ]]; then
    echo "$(date '+%Y-%m-%d %H:%M:%S') - ERROR: ANTHROPIC_API_KEY not found in Keychain or .env" >> "$ERROR_LOG"
    exit 1
fi

# ─────────────────────────────────────────────────────────────────────
# Exponential Backoff Retry Logic
# ─────────────────────────────────────────────────────────────────────
if [[ -f "$RETRY_STATE" ]]; then
    RETRY_COUNT=$(cat "$RETRY_STATE")
else
    RETRY_COUNT=0
fi

# Calculate retry delay (2, 4, 8, 16... capped at 86400s = 1 day)
if [[ $RETRY_COUNT -gt 0 ]]; then
    DELAY=$((2 ** RETRY_COUNT))
    if [[ $DELAY -gt 86400 ]]; then
        DELAY=86400
    fi
    echo "$(date '+%Y-%m-%d %H:%M:%S') - Retry attempt $RETRY_COUNT after waiting ${DELAY}s"
    sleep $DELAY
fi

# ─────────────────────────────────────────────────────────────────────
# Run email-nurse
# ─────────────────────────────────────────────────────────────────────
if "$INSTALL_DIR/venv/bin/email-nurse" autopilot run -v --auto-create; then
    # Success - reset retry counter
    rm -f "$RETRY_STATE"
    echo "$(date '+%Y-%m-%d %H:%M:%S') - SUCCESS"
else
    EXIT_CODE=$?
    # Increment retry counter
    echo $((RETRY_COUNT + 1)) > "$RETRY_STATE"

    # Log failure
    {
        echo ""
        echo "════════════════════════════════════════════════════════════════"
        echo "$(date '+%Y-%m-%d %H:%M:%S')"
        echo "Exit Code: $EXIT_CODE"
        echo "Retry Count: $((RETRY_COUNT + 1))"
        echo "════════════════════════════════════════════════════════════════"
        echo ""
    } >> "$ERROR_LOG"

    exit $EXIT_CODE
fi
