#!/bin/zsh
#
# email-nurse doctor
# Diagnose installation health and identify issues
#
# Usage:
#   ./scripts/doctor.sh         # Run full diagnostics
#   ./scripts/doctor.sh --fix   # Attempt to fix common issues
#

set -e

# ─────────────────────────────────────────────────────────────────────────────
# Configuration
# ─────────────────────────────────────────────────────────────────────────────

INSTALL_BASE="$HOME/.local/share/email-nurse"
INSTALL_DIR="$INSTALL_BASE/current"
BIN_DIR="$HOME/.local/bin"
CONFIG_DIR="$HOME/.config/email-nurse"
STATE_DIR="$HOME/.local/state/email-nurse"
LOG_DIR="$HOME/Library/Logs"
PLIST_DIR="$HOME/Library/LaunchAgents"

# Keychain service names
ANTHROPIC_SERVICE="email-nurse-anthropic"
OPENAI_SERVICE="email-nurse-openai"

# LaunchAgent names
INTERVAL_PLIST="com.bss.email-nurse.plist"
WATCHER_PLIST="com.bss.email-nurse-watcher.plist"
REPORT_PLIST="com.bss.email-nurse-report.plist"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
DIM='\033[2m'
NC='\033[0m'

# Counters
PASS=0
WARN=0
FAIL=0

# ─────────────────────────────────────────────────────────────────────────────
# Helper Functions
# ─────────────────────────────────────────────────────────────────────────────

pass() {
    echo "${GREEN}✓${NC} $1"
    PASS=$((PASS + 1))
}

warn() {
    echo "${YELLOW}⚠${NC} $1"
    WARN=$((WARN + 1))
}

fail() {
    echo "${RED}✗${NC} $1"
    FAIL=$((FAIL + 1))
}

info() {
    echo "${DIM}○${NC} $1"
}

check_keychain() {
    local service="$1"
    security find-generic-password -a "$USER" -s "$service" -w >/dev/null 2>&1
}

get_launchctl_state() {
    local label="$1"
    # Returns: running PID, or exit code, or empty if not loaded
    launchctl list 2>/dev/null | grep "$label" | awk '{print $1}'
}

# ─────────────────────────────────────────────────────────────────────────────
# Checks
# ─────────────────────────────────────────────────────────────────────────────

check_installation() {
    echo "${BOLD}Installation${NC}"
    echo "───────────────────────────────────────"

    # Check symlink exists
    if [[ -L "$INSTALL_DIR" ]]; then
        local target=$(readlink "$INSTALL_DIR")
        local version=$(cat "$INSTALL_DIR/VERSION" 2>/dev/null || echo "unknown")
        pass "Symlink: current -> $(basename "$target")"

        # Check venv
        if [[ -d "$INSTALL_DIR/venv" ]]; then
            if "$INSTALL_DIR/venv/bin/email-nurse" --help >/dev/null 2>&1; then
                pass "Virtual environment: working (v$version)"
            else
                fail "Virtual environment: broken - run install.sh --force"
            fi
        else
            fail "Virtual environment: missing - run install.sh"
        fi
    else
        fail "Installation not found at $INSTALL_DIR"
        echo "     Run: ${CYAN}./scripts/install.sh${NC}"
    fi

    # Check scripts
    local scripts=("email-nurse-autopilot.sh" "email-nurse-watcher.sh" "email-nurse-logs.sh")
    local missing_scripts=()
    for script in "${scripts[@]}"; do
        if [[ ! -x "$BIN_DIR/$script" ]]; then
            missing_scripts+=("$script")
        fi
    done
    if [[ ${#missing_scripts[@]} -eq 0 ]]; then
        pass "Launch scripts: all present in $BIN_DIR"
    else
        warn "Launch scripts missing: ${missing_scripts[*]}"
    fi

    echo ""
}

check_keychain_keys() {
    echo "${BOLD}API Keys (Keychain)${NC}"
    echo "───────────────────────────────────────"

    if check_keychain "$ANTHROPIC_SERVICE"; then
        pass "ANTHROPIC_API_KEY: found in Keychain"
    else
        fail "ANTHROPIC_API_KEY: not found in Keychain"
        echo "     Run: ${CYAN}./scripts/keychain.sh migrate${NC} or ${CYAN}./scripts/keychain.sh add${NC}"
    fi

    if check_keychain "$OPENAI_SERVICE"; then
        pass "OPENAI_API_KEY: found in Keychain ${DIM}(optional)${NC}"
    else
        info "OPENAI_API_KEY: not found ${DIM}(optional, for OpenAI provider)${NC}"
    fi

    echo ""
}

check_config() {
    echo "${BOLD}Configuration${NC}"
    echo "───────────────────────────────────────"

    # Required config
    if [[ -f "$CONFIG_DIR/autopilot.yaml" ]]; then
        pass "autopilot.yaml: exists"
    else
        fail "autopilot.yaml: missing"
        echo "     Run: ${CYAN}./scripts/install.sh${NC} or copy from config/"
    fi

    # Optional configs
    if [[ -f "$CONFIG_DIR/rules.yaml" ]]; then
        pass "rules.yaml: exists ${DIM}(quick rules)${NC}"
    else
        info "rules.yaml: not found ${DIM}(optional)${NC}"
    fi

    if [[ -f "$CONFIG_DIR/.env" ]]; then
        # Check if it contains API keys (security warning)
        if grep -q "API_KEY" "$CONFIG_DIR/.env" 2>/dev/null; then
            warn ".env: contains API keys - migrate to Keychain for security"
            echo "     Run: ${CYAN}./scripts/keychain.sh migrate${NC}"
        else
            pass ".env: exists ${DIM}(no sensitive keys)${NC}"
        fi
    else
        info ".env: not found ${DIM}(optional)${NC}"
    fi

    echo ""
}

check_launchagents() {
    echo "${BOLD}LaunchAgents${NC}"
    echo "───────────────────────────────────────"

    # Check interval agent
    if [[ -f "$PLIST_DIR/$INTERVAL_PLIST" ]]; then
        local agent_state=$(get_launchctl_state "com.bss.email-nurse")
        if [[ -n "$agent_state" ]]; then
            if [[ "$agent_state" == "-" ]]; then
                pass "Interval mode: installed, idle ${DIM}(runs every 9 min)${NC}"
            elif [[ "$agent_state" =~ ^[0-9]+$ ]]; then
                pass "Interval mode: running (PID $agent_state)"
            else
                warn "Interval mode: installed, last exit code $agent_state"
            fi
        else
            info "Interval mode: installed but not loaded"
        fi
    else
        info "Interval mode: not installed"
    fi

    # Check watcher agent
    if [[ -f "$PLIST_DIR/$WATCHER_PLIST" ]]; then
        local agent_state=$(get_launchctl_state "com.bss.email-nurse-watcher")
        if [[ -n "$agent_state" ]]; then
            if [[ "$agent_state" == "-" ]]; then
                # Check if it's actually running
                if pgrep -f "email-nurse autopilot watch" >/dev/null 2>&1; then
                    local pid=$(pgrep -f "email-nurse autopilot watch")
                    pass "Watcher mode: ${GREEN}running${NC} (PID $pid)"
                else
                    warn "Watcher mode: loaded but not running"
                    if ! pgrep -xq "Mail"; then
                        echo "     ${DIM}Mail.app is not running - watcher waits for it${NC}"
                    elif ! check_keychain "$ANTHROPIC_SERVICE"; then
                        echo "     ${DIM}Missing Keychain entry - run keychain.sh migrate${NC}"
                    fi
                fi
            elif [[ "$agent_state" =~ ^[0-9]+$ ]]; then
                pass "Watcher mode: running (PID $agent_state)"
            else
                warn "Watcher mode: installed, last exit code $agent_state"
            fi
        else
            info "Watcher mode: installed but not loaded"
        fi
    else
        info "Watcher mode: not installed"
    fi

    # Check report agent
    if [[ -f "$PLIST_DIR/$REPORT_PLIST" ]]; then
        local report_state=$(get_launchctl_state "com.bss.email-nurse-report")
        if [[ -n "$report_state" ]]; then
            pass "Daily report: installed and loaded"
        else
            info "Daily report: installed but not loaded"
        fi
    else
        info "Daily report: not installed ${DIM}(optional)${NC}"
    fi

    echo ""
}

check_database() {
    echo "${BOLD}Database & State${NC}"
    echo "───────────────────────────────────────"

    local db_file="$STATE_DIR/autopilot.db"

    if [[ -f "$db_file" ]]; then
        # Get stats
        local processed=$(sqlite3 "$db_file" "SELECT COUNT(*) FROM processed_emails" 2>/dev/null || echo "0")
        local last_processed=$(sqlite3 "$db_file" "SELECT MAX(processed_at) FROM processed_emails" 2>/dev/null || echo "never")
        local pending=$(sqlite3 "$db_file" "SELECT COUNT(*) FROM pending_actions WHERE status='pending'" 2>/dev/null || echo "0")

        pass "Database: $db_file"
        echo "     ${DIM}Processed: $processed emails${NC}"

        if [[ "$last_processed" != "never" && -n "$last_processed" ]]; then
            # Parse and format the date
            local last_date="${last_processed:0:10}"
            local days_ago=$(( ($(date +%s) - $(date -j -f "%Y-%m-%d" "$last_date" +%s 2>/dev/null || echo $(date +%s))) / 86400 ))

            if [[ $days_ago -eq 0 ]]; then
                pass "Last activity: today"
            elif [[ $days_ago -eq 1 ]]; then
                pass "Last activity: yesterday"
            elif [[ $days_ago -lt 7 ]]; then
                pass "Last activity: $days_ago days ago"
            else
                warn "Last activity: $days_ago days ago - is the watcher running?"
            fi
        else
            warn "Last activity: never processed any emails"
        fi

        if [[ "$pending" -gt 0 ]]; then
            warn "Pending actions: $pending awaiting approval"
            echo "     Run: ${CYAN}email-nurse autopilot queue${NC}"
        else
            pass "Pending actions: none"
        fi
    else
        warn "Database: not found (will be created on first run)"
    fi

    echo ""
}

check_mail_app() {
    echo "${BOLD}Mail.app${NC}"
    echo "───────────────────────────────────────"

    if pgrep -xq "Mail"; then
        pass "Mail.app: running"

        # Test AppleScript access
        if osascript -e 'tell application "Mail" to count of accounts' >/dev/null 2>&1; then
            local account_count=$(osascript -e 'tell application "Mail" to count of accounts' 2>/dev/null)
            pass "AppleScript access: granted ($account_count accounts)"
        else
            fail "AppleScript access: denied"
            echo "     Grant access in System Settings > Privacy & Security > Automation"
        fi
    else
        warn "Mail.app: not running"
        echo "     ${DIM}Watcher will start automatically when Mail.app opens${NC}"
    fi

    echo ""
}

check_logs() {
    echo "${BOLD}Logs${NC}"
    echo "───────────────────────────────────────"

    local log_files=(
        "email-nurse.log"
        "email-nurse-error.log"
        "email-nurse-watcher.log"
        "email-nurse-watcher-error.log"
    )

    for log in "${log_files[@]}"; do
        local log_path="$LOG_DIR/$log"
        if [[ -f "$log_path" ]]; then
            local size=$(ls -lh "$log_path" | awk '{print $5}')
            local modified=$(stat -f "%Sm" -t "%Y-%m-%d %H:%M" "$log_path")
            info "$log: $size (modified $modified)"
        fi
    done

    echo "     View logs: ${CYAN}~/.local/bin/email-nurse-logs.sh${NC}"
    echo ""
}

# ─────────────────────────────────────────────────────────────────────────────
# Summary
# ─────────────────────────────────────────────────────────────────────────────

show_summary() {
    echo "${BOLD}═══════════════════════════════════════${NC}"
    echo "${BOLD}Summary${NC}"
    echo "${BOLD}═══════════════════════════════════════${NC}"
    echo ""

    echo "  ${GREEN}✓ Passed:${NC}  $PASS"
    echo "  ${YELLOW}⚠ Warnings:${NC} $WARN"
    echo "  ${RED}✗ Failed:${NC}  $FAIL"
    echo ""

    if [[ $FAIL -eq 0 && $WARN -eq 0 ]]; then
        echo "  ${GREEN}${BOLD}All checks passed!${NC}"
    elif [[ $FAIL -eq 0 ]]; then
        echo "  ${YELLOW}${BOLD}Some warnings - review above${NC}"
    else
        echo "  ${RED}${BOLD}Issues found - see above for fixes${NC}"
    fi
    echo ""
}

# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

echo ""
echo "${BOLD}${CYAN}═══════════════════════════════════════════════════════════${NC}"
echo "${BOLD}           email-nurse Doctor${NC}"
echo "${BOLD}${CYAN}═══════════════════════════════════════════════════════════${NC}"
echo ""

check_installation
check_keychain_keys
check_config
check_launchagents
check_database
check_mail_app
check_logs
show_summary
