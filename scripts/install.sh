#!/bin/zsh
#
# email-nurse install script
# Installs email-nurse to ~/.local/ with LaunchAgent for scheduled runs
#
# Usage:
#   ./scripts/install.sh           # Install or upgrade
#   ./scripts/install.sh --force   # Force reinstall current version
#

set -e

# ─────────────────────────────────────────────────────────────────────────────
# Configuration
# ─────────────────────────────────────────────────────────────────────────────

REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
INSTALL_BASE="$HOME/.local/share/email-nurse"
BIN_DIR="$HOME/.local/bin"
STATE_DIR="$HOME/.local/state/email-nurse"
CONFIG_DIR="$HOME/.config/email-nurse"
LOG_DIR="$HOME/Library/Logs"
PLIST_DIR="$HOME/Library/LaunchAgents"
PLIST_NAME="com.bss.email-nurse.plist"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

# ─────────────────────────────────────────────────────────────────────────────
# Helper Functions
# ─────────────────────────────────────────────────────────────────────────────

info() { echo "${CYAN}▶${NC} $1"; }
success() { echo "${GREEN}✓${NC} $1"; }
warn() { echo "${YELLOW}⚠${NC} $1"; }
error() { echo "${RED}✗${NC} $1"; exit 1; }

get_version() {
    cd "$REPO_DIR"
    git describe --tags --always 2>/dev/null || echo "dev"
}

check_keychain_secret() {
    local service="$1"
    security find-generic-password -a "$USER" -s "$service" -w >/dev/null 2>&1
}

# ─────────────────────────────────────────────────────────────────────────────
# Main Installation
# ─────────────────────────────────────────────────────────────────────────────

echo ""
echo "${BOLD}${CYAN}═══════════════════════════════════════════════════════════${NC}"
echo "${BOLD}           email-nurse Installation${NC}"
echo "${BOLD}${CYAN}═══════════════════════════════════════════════════════════${NC}"
echo ""

VERSION=$(get_version)
INSTALL_DIR="$INSTALL_BASE/versions/$VERSION"
FORCE_INSTALL=false

if [[ "$1" == "--force" ]]; then
    FORCE_INSTALL=true
    warn "Force install requested"
fi

# Check if already installed
if [[ -d "$INSTALL_DIR" && "$FORCE_INSTALL" == "false" ]]; then
    CURRENT=$(readlink "$INSTALL_BASE/current" 2>/dev/null | xargs basename 2>/dev/null || echo "none")
    if [[ "$CURRENT" == "$VERSION" ]]; then
        success "Version $VERSION already installed and active"
        echo "  Use --force to reinstall"
        exit 0
    fi
fi

# ─────────────────────────────────────────────────────────────────────────────
# Step 1: Create Directories
# ─────────────────────────────────────────────────────────────────────────────

info "Creating directories..."
mkdir -p "$BIN_DIR"
mkdir -p "$INSTALL_BASE/versions"
mkdir -p "$STATE_DIR"
mkdir -p "$CONFIG_DIR"
mkdir -p "$LOG_DIR"
mkdir -p "$PLIST_DIR"
success "Directories created"

# ─────────────────────────────────────────────────────────────────────────────
# Step 2: Build Virtual Environment
# ─────────────────────────────────────────────────────────────────────────────

info "Building virtual environment for version $VERSION..."

# Remove existing version if force install
if [[ -d "$INSTALL_DIR" ]]; then
    rm -rf "$INSTALL_DIR"
fi

mkdir -p "$INSTALL_DIR"
python3 -m venv "$INSTALL_DIR/venv"
"$INSTALL_DIR/venv/bin/pip" install -q --upgrade pip
"$INSTALL_DIR/venv/bin/pip" install -q "$REPO_DIR"
echo "$VERSION" > "$INSTALL_DIR/VERSION"

# Verify installation
if ! "$INSTALL_DIR/venv/bin/email-nurse" --help >/dev/null 2>&1; then
    error "Installation verification failed"
fi

success "Built version $VERSION"

# ─────────────────────────────────────────────────────────────────────────────
# Step 3: Update Symlink
# ─────────────────────────────────────────────────────────────────────────────

info "Activating version $VERSION..."
ln -sfn "$INSTALL_DIR" "$INSTALL_BASE/current"
success "Symlink updated: current -> $VERSION"

# ─────────────────────────────────────────────────────────────────────────────
# Step 4: Check/Setup API Key
# ─────────────────────────────────────────────────────────────────────────────

echo ""
info "Checking API key in Keychain..."

if check_keychain_secret "email-nurse-anthropic"; then
    success "ANTHROPIC_API_KEY found in Keychain"
else
    warn "ANTHROPIC_API_KEY not found in Keychain"
    echo ""
    echo "  To add your API key, run:"
    echo "  ${CYAN}security add-generic-password -a \"\$USER\" -s \"email-nurse-anthropic\" -w \"sk-ant-...\"${NC}"
    echo ""
    read -q "REPLY?Would you like to add it now? [y/N] "
    echo ""
    if [[ "$REPLY" =~ ^[Yy]$ ]]; then
        echo -n "Enter your Anthropic API key: "
        read -s API_KEY
        echo ""
        if [[ -n "$API_KEY" ]]; then
            security add-generic-password -a "$USER" -s "email-nurse-anthropic" -w "$API_KEY" -U
            success "API key stored in Keychain"
        else
            warn "No API key provided, skipping"
        fi
    fi
fi

# ─────────────────────────────────────────────────────────────────────────────
# Step 5: Install Launch Scripts
# ─────────────────────────────────────────────────────────────────────────────

info "Installing launch scripts..."

# Autopilot script
cat > "$BIN_DIR/email-nurse-autopilot.sh" << 'AUTOPILOT_EOF'
#!/bin/zsh

# email-nurse-autopilot.sh
# System-installed launcher for email-nurse (repo-independent)
#
# Paths:
#   Install:  ~/.local/share/email-nurse/current/
#   Config:   ~/.config/email-nurse/
#   State:    ~/.local/state/email-nurse/
#   Logs:     ~/Library/Logs/
#   Secrets:  macOS Keychain

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
# Load Secrets from macOS Keychain
# ─────────────────────────────────────────────────────────────────────
export ANTHROPIC_API_KEY=$(security find-generic-password -a "$USER" \
    -s "email-nurse-anthropic" -w 2>/dev/null)

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
    # Load all vars EXCEPT API keys (those come from Keychain)
    while IFS='=' read -r key value; do
        # Skip comments, empty lines, and API keys
        [[ "$key" =~ ^#.*$ || -z "$key" || "$key" =~ .*API_KEY.* ]] && continue
        # Remove quotes from value
        value="${value%\"}"
        value="${value#\"}"
        value="${value%\'}"
        value="${value#\'}"
        export "$key=$value"
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
    echo "$(date '+%Y-%m-%d %H:%M:%S') - ERROR: ANTHROPIC_API_KEY not found in Keychain" >> "$ERROR_LOG"
    echo "Run: security add-generic-password -a \"\$USER\" -s \"email-nurse-anthropic\" -w \"sk-ant-...\"" >> "$ERROR_LOG"
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
        echo "Error Log: $ERROR_LOG"
        echo "Output Log: $OUTPUT_LOG"
        echo "LaunchAgent Config: $PLIST_PATH"
        echo "Installation: $INSTALL_DIR"
        echo ""
        echo "███████╗ █████╗ ██╗██╗     ██╗   ██╗██████╗ ███████╗"
        echo "██╔════╝██╔══██╗██║██║     ██║   ██║██╔══██╗██╔════╝"
        echo "█████╗  ███████║██║██║     ██║   ██║██████╔╝█████╗  "
        echo "██╔══╝  ██╔══██║██║██║     ██║   ██║██╔══██╗██╔══╝  "
        echo "██║     ██║  ██║██║███████╗╚██████╔╝██║  ██║███████╗"
        echo "╚═╝     ╚═╝  ╚═╝╚═╝╚══════╝ ╚═════╝ ╚═╝  ╚═╝╚══════╝"
        echo ""
        echo "Exit Code: $EXIT_CODE"
        echo "Retry Count: $((RETRY_COUNT + 1))"
        echo "Next Retry In: $((2 ** (RETRY_COUNT + 1) > 86400 ? 86400 : 2 ** (RETRY_COUNT + 1)))s"
        echo "════════════════════════════════════════════════════════════════"
        echo ""
    } >> "$ERROR_LOG"

    exit $EXIT_CODE
fi
AUTOPILOT_EOF

chmod +x "$BIN_DIR/email-nurse-autopilot.sh"

# Log viewer script
cat > "$BIN_DIR/email-nurse-logs.sh" << 'LOGS_EOF'
#!/bin/zsh

# email-nurse-logs.sh
# Interactive log viewer for email-nurse

LOG_DIR="$HOME/Library/Logs"
MAIN_LOG="${LOG_DIR}/email-nurse.log"
ERROR_LOG="${LOG_DIR}/email-nurse-error.log"

# Colors
BOLD='\033[1m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
RED='\033[0;31m'
CYAN='\033[0;36m'
NC='\033[0m'

show_menu() {
    clear
    echo "${BOLD}${CYAN}═══════════════════════════════════════${NC}"
    echo "${BOLD}       Email Nurse Log Viewer${NC}"
    echo "${BOLD}${CYAN}═══════════════════════════════════════${NC}"
    echo ""
    echo "  ${GREEN}1)${NC} Tail main log      ${YELLOW}(email-nurse.log)${NC}"
    echo "  ${GREEN}2)${NC} Tail error log     ${YELLOW}(email-nurse-error.log)${NC}"
    echo "  ${GREEN}3)${NC} Tail both logs     ${YELLOW}(simultaneous)${NC}"
    echo "  ${GREEN}4)${NC} Show last 50 lines ${YELLOW}(main log)${NC}"
    echo "  ${GREEN}5)${NC} Show last 50 lines ${YELLOW}(error log)${NC}"
    echo "  ${RED}q)${NC} Quit"
    echo ""
    echo "${CYAN}───────────────────────────────────────${NC}"
    echo "  Press ${BOLD}Ctrl+C${NC} while viewing to return here"
    echo "${CYAN}───────────────────────────────────────${NC}"
    echo ""
}

tail_log() {
    local log_file="$1"
    local log_name="$2"
    if [[ ! -f "$log_file" ]]; then
        echo "${RED}Error: ${log_file} not found${NC}"
        echo "Press Enter to continue..."
        read
        return
    fi
    echo ""
    echo "${BOLD}${CYAN}>>> Tailing ${log_name}...${NC}"
    echo "${YELLOW}    Press Ctrl+C to return to menu${NC}"
    echo ""
    tail -f "$log_file"
}

tail_both() {
    if [[ ! -f "$MAIN_LOG" && ! -f "$ERROR_LOG" ]]; then
        echo "${RED}Error: No log files found${NC}"
        echo "Press Enter to continue..."
        read
        return
    fi
    echo ""
    echo "${BOLD}${CYAN}>>> Tailing both logs...${NC}"
    echo "${YELLOW}    Press Ctrl+C to return to menu${NC}"
    echo ""
    tail -f "$MAIN_LOG" "$ERROR_LOG" 2>/dev/null
}

show_last() {
    local log_file="$1"
    local log_name="$2"
    if [[ ! -f "$log_file" ]]; then
        echo "${RED}Error: ${log_file} not found${NC}"
        echo "Press Enter to continue..."
        read
        return
    fi
    echo ""
    echo "${BOLD}${CYAN}>>> Last 50 lines of ${log_name}${NC}"
    echo ""
    tail -n 50 "$log_file"
    echo ""
    echo "${YELLOW}Press Enter to continue...${NC}"
    read
}

while true; do
    show_menu
    echo -n "  Select option [1-5, q]: "
    read choice
    case "$choice" in
        1) trap 'echo ""; continue' INT; tail_log "$MAIN_LOG" "main log"; trap - INT ;;
        2) trap 'echo ""; continue' INT; tail_log "$ERROR_LOG" "error log"; trap - INT ;;
        3) trap 'echo ""; continue' INT; tail_both; trap - INT ;;
        4) show_last "$MAIN_LOG" "main log" ;;
        5) show_last "$ERROR_LOG" "error log" ;;
        q|Q) echo ""; echo "${GREEN}Goodbye!${NC}"; exit 0 ;;
        *) echo "${RED}Invalid option${NC}"; sleep 1 ;;
    esac
done
LOGS_EOF

chmod +x "$BIN_DIR/email-nurse-logs.sh"

# Watcher script (hybrid triggers - polls for new messages + interval)
cat > "$BIN_DIR/email-nurse-watcher.sh" << 'WATCHER_EOF'
#!/bin/zsh

# email-nurse-watcher.sh
# System-installed launcher for email-nurse watcher (repo-independent)
#
# This script runs the continuous watcher process that monitors for new
# emails and triggers scans based on hybrid triggers (new messages + interval).
#
# Paths:
#   Install:  ~/.local/share/email-nurse/current/
#   Config:   ~/.config/email-nurse/
#   State:    ~/.local/state/email-nurse/
#   Logs:     ~/Library/Logs/
#   Secrets:  macOS Keychain

# Strict mode
set -o pipefail

# Paths
INSTALL_DIR="$HOME/.local/share/email-nurse/current"
CONFIG_DIR="$HOME/.config/email-nurse"
STATE_DIR="$HOME/.local/state/email-nurse"
LOG_DIR="$HOME/Library/Logs"

# Log files
ERROR_LOG="${LOG_DIR}/email-nurse-watcher-error.log"
OUTPUT_LOG="${LOG_DIR}/email-nurse-watcher.log"

# Ensure state directory exists
mkdir -p "$STATE_DIR"

# ─────────────────────────────────────────────────────────────────────
# Skip if Mail.app is not running
# ─────────────────────────────────────────────────────────────────────
if ! pgrep -xq "Mail"; then
    echo "$(date '+%Y-%m-%d %H:%M:%S') - Mail.app not running, exiting"
    exit 0
fi

# ─────────────────────────────────────────────────────────────────────
# Load Secrets from macOS Keychain
# ─────────────────────────────────────────────────────────────────────
export ANTHROPIC_API_KEY=$(security find-generic-password -a "$USER" \
    -s "email-nurse-anthropic" -w 2>/dev/null)

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
    # Load all vars EXCEPT API keys (those come from Keychain)
    while IFS='=' read -r key value; do
        # Skip comments, empty lines, and API keys
        [[ "$key" =~ ^#.*$ || -z "$key" || "$key" =~ .*API_KEY.* ]] && continue
        # Remove quotes from value
        value="${value%\"}"
        value="${value#\"}"
        value="${value%\'}"
        value="${value#\'}"
        export "$key=$value"
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
    echo "$(date '+%Y-%m-%d %H:%M:%S') - ERROR: ANTHROPIC_API_KEY not found in Keychain" >> "$ERROR_LOG"
    echo "Run: security add-generic-password -a \"\$USER\" -s \"email-nurse-anthropic\" -w \"sk-ant-...\"" >> "$ERROR_LOG"
    exit 1
fi

# ─────────────────────────────────────────────────────────────────────
# Run email-nurse watcher
# ─────────────────────────────────────────────────────────────────────
echo "$(date '+%Y-%m-%d %H:%M:%S') - Starting watcher process"

# The watcher is a long-running process. KeepAlive in the LaunchAgent
# will restart it if it exits. No manual retry logic needed.
exec "$INSTALL_DIR/venv/bin/email-nurse" autopilot watch -v --auto-create
WATCHER_EOF

chmod +x "$BIN_DIR/email-nurse-watcher.sh"

# Digest script (daily report)
cat > "$BIN_DIR/email-nurse-digest.sh" << 'DIGEST_EOF'
#!/bin/zsh

# email-nurse-digest.sh
# Daily digest report sender for email-nurse

set -o pipefail

INSTALL_DIR="$HOME/.local/share/email-nurse/current"
CONFIG_DIR="$HOME/.config/email-nurse"
LOG_DIR="$HOME/Library/Logs"

log() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') - $1"
}

log "Starting daily digest"

# Skip if Mail.app is not running
if ! pgrep -xq "Mail"; then
    log "Mail.app not running, skipping digest"
    exit 0
fi

# Load non-sensitive config from .env
if [[ -f "$CONFIG_DIR/.env" ]]; then
    while IFS='=' read -r key value; do
        [[ "$key" =~ ^#.*$ || -z "$key" || "$key" =~ .*API_KEY.* ]] && continue
        value="${value%\"}"
        value="${value#\"}"
        value="${value%\'}"
        value="${value#\'}"
        export "$key=$value"
    done < "$CONFIG_DIR/.env"
fi

# Verify installation
if [[ ! -d "$INSTALL_DIR/venv" ]]; then
    log "ERROR: Installation not found at $INSTALL_DIR"
    exit 1
fi

# Send daily digest
if "$INSTALL_DIR/venv/bin/email-nurse" autopilot report; then
    log "SUCCESS - Digest sent"
else
    EXIT_CODE=$?
    log "FAILED - Exit code: $EXIT_CODE"
    exit $EXIT_CODE
fi
DIGEST_EOF

chmod +x "$BIN_DIR/email-nurse-digest.sh"

success "Launch scripts installed"

# ─────────────────────────────────────────────────────────────────────────────
# Step 5b: Install Management Scripts
# ─────────────────────────────────────────────────────────────────────────────

info "Installing management scripts..."

# Copy management scripts from repo
for script in keychain.sh doctor.sh mode.sh; do
    if [[ -f "$REPO_DIR/scripts/$script" ]]; then
        cp "$REPO_DIR/scripts/$script" "$BIN_DIR/email-nurse-${script%.sh}"
        chmod +x "$BIN_DIR/email-nurse-${script%.sh}"
    fi
done

success "Management scripts installed"

# ─────────────────────────────────────────────────────────────────────────────
# Step 6: Install LaunchAgent
# ─────────────────────────────────────────────────────────────────────────────

info "Installing LaunchAgent..."

# Unload existing if present
launchctl unload "$PLIST_DIR/$PLIST_NAME" 2>/dev/null || true

# Create plist
cat > "$PLIST_DIR/$PLIST_NAME" << PLIST_EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.bss.email-nurse</string>

    <key>ProgramArguments</key>
    <array>
        <string>$BIN_DIR/email-nurse-autopilot.sh</string>
    </array>

    <key>StartInterval</key>
    <integer>540</integer>

    <key>RunAtLoad</key>
    <true/>

    <key>StandardOutPath</key>
    <string>$LOG_DIR/email-nurse.log</string>

    <key>StandardErrorPath</key>
    <string>$LOG_DIR/email-nurse-error.log</string>

    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin</string>
    </dict>
</dict>
</plist>
PLIST_EOF

# Load the agent
launchctl load "$PLIST_DIR/$PLIST_NAME"

success "LaunchAgent installed and loaded"

# ─────────────────────────────────────────────────────────────────────────────
# Step 6b: Install Watcher LaunchAgent (not loaded by default)
# ─────────────────────────────────────────────────────────────────────────────

WATCHER_PLIST_NAME="com.bss.email-nurse-watcher.plist"

info "Installing Watcher LaunchAgent (not enabled by default)..."

# Unload existing if present
launchctl unload "$PLIST_DIR/$WATCHER_PLIST_NAME" 2>/dev/null || true

# Create watcher plist
cat > "$PLIST_DIR/$WATCHER_PLIST_NAME" << WATCHER_PLIST_EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.bss.email-nurse-watcher</string>

    <key>ProgramArguments</key>
    <array>
        <string>$BIN_DIR/email-nurse-watcher.sh</string>
    </array>

    <!-- KeepAlive: restart if process exits -->
    <key>KeepAlive</key>
    <dict>
        <!-- Only run when Mail.app is running -->
        <key>OtherJobEnabled</key>
        <dict>
            <key>com.apple.mail</key>
            <true/>
        </dict>
    </dict>

    <key>RunAtLoad</key>
    <true/>

    <!-- Throttle restarts to avoid tight loops on failure -->
    <key>ThrottleInterval</key>
    <integer>60</integer>

    <key>StandardOutPath</key>
    <string>$LOG_DIR/email-nurse-watcher.log</string>

    <key>StandardErrorPath</key>
    <string>$LOG_DIR/email-nurse-watcher-error.log</string>

    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin</string>
    </dict>
</dict>
</plist>
WATCHER_PLIST_EOF

success "Watcher LaunchAgent installed (run 'email-nurse-enable-watcher' to switch modes)"

# ─────────────────────────────────────────────────────────────────────────────
# Step 6c: Install Digest LaunchAgent (daily report at 21:00)
# ─────────────────────────────────────────────────────────────────────────────

DIGEST_PLIST_NAME="com.bss.email-nurse-digest.plist"

info "Installing Digest LaunchAgent (daily at 21:00)..."

# Unload existing if present
launchctl unload "$PLIST_DIR/$DIGEST_PLIST_NAME" 2>/dev/null || true

# Create digest plist
cat > "$PLIST_DIR/$DIGEST_PLIST_NAME" << DIGEST_PLIST_EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.bss.email-nurse-digest</string>

    <key>ProgramArguments</key>
    <array>
        <string>$BIN_DIR/email-nurse-digest.sh</string>
    </array>

    <!-- Run daily at 21:00 (9 PM) -->
    <key>StartCalendarInterval</key>
    <dict>
        <key>Hour</key>
        <integer>21</integer>
        <key>Minute</key>
        <integer>0</integer>
    </dict>

    <key>StandardOutPath</key>
    <string>$LOG_DIR/email-nurse-digest.log</string>

    <key>StandardErrorPath</key>
    <string>$LOG_DIR/email-nurse-digest.log</string>

    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin</string>
    </dict>
</dict>
</plist>
DIGEST_PLIST_EOF

# Load the agent
launchctl load "$PLIST_DIR/$DIGEST_PLIST_NAME"

success "Digest LaunchAgent installed (sends daily report at 21:00)"

# ─────────────────────────────────────────────────────────────────────────────
# Step 7: Copy Example Configs (if needed)
# ─────────────────────────────────────────────────────────────────────────────

if [[ ! -f "$CONFIG_DIR/autopilot.yaml" ]]; then
    info "Copying example configuration files..."
    cp "$REPO_DIR/config/autopilot.yaml.example" "$CONFIG_DIR/autopilot.yaml" 2>/dev/null || true
    cp "$REPO_DIR/config/rules.yaml.example" "$CONFIG_DIR/rules.yaml" 2>/dev/null || true
    cp "$REPO_DIR/config/templates.yaml.example" "$CONFIG_DIR/templates.yaml" 2>/dev/null || true
    success "Example configs copied to $CONFIG_DIR"
fi

# ─────────────────────────────────────────────────────────────────────────────
# Done!
# ─────────────────────────────────────────────────────────────────────────────

echo ""
echo "${BOLD}${GREEN}═══════════════════════════════════════════════════════════${NC}"
echo "${BOLD}${GREEN}           Installation Complete!${NC}"
echo "${BOLD}${GREEN}═══════════════════════════════════════════════════════════${NC}"
echo ""
echo "  Version:     ${CYAN}$VERSION${NC}"
echo "  Install:     ${CYAN}$INSTALL_BASE/current${NC}"
echo "  Config:      ${CYAN}$CONFIG_DIR${NC}"
echo "  Logs:        ${CYAN}$LOG_DIR/email-nurse.log${NC}"
echo ""
echo "  ${BOLD}Management Commands:${NC}"
echo "    ${CYAN}email-nurse-doctor${NC}    Health check and diagnostics"
echo "    ${CYAN}email-nurse-mode${NC}      Switch between interval/watcher modes"
echo "    ${CYAN}email-nurse-keychain${NC}  Manage API keys in Keychain"
echo "    ${CYAN}email-nurse-logs${NC}      Interactive log viewer"
echo ""
echo "  ${BOLD}Trigger Modes:${NC}"
echo ""
echo "    ${YELLOW}Interval Mode (default - currently active):${NC}"
echo "      Runs every 9 minutes when Mail.app is open"
echo ""
echo "    ${YELLOW}Watcher Mode (hybrid triggers - recommended):${NC}"
echo "      Polls inbox every 30s + triggers immediately on new mail"
echo "      Switch with: ${CYAN}email-nurse-mode watcher${NC}"
echo ""
echo "  ${BOLD}Daily Digest:${NC}"
echo "    Sends daily activity report at 21:00"
echo "    Logs: ${CYAN}$LOG_DIR/email-nurse-digest.log${NC}"
echo "    Test now: ${CYAN}launchctl start com.bss.email-nurse-digest${NC}"
echo ""

# Migrate API keys if found in .env
if [[ -f "$CONFIG_DIR/.env" ]] && grep -q "API_KEY" "$CONFIG_DIR/.env" 2>/dev/null; then
    echo "  ${YELLOW}⚠ API keys found in .env file${NC}"
    echo "    Run ${CYAN}email-nurse-keychain migrate${NC} to move to Keychain"
    echo ""
fi

# Run doctor check
echo "  ${BOLD}Running health check...${NC}"
echo ""
"$BIN_DIR/email-nurse-doctor" 2>/dev/null || true
echo ""
