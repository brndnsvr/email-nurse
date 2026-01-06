#!/bin/zsh
#
# email-nurse mode switching
# Switch between interval and watcher trigger modes
#
# Usage:
#   ./scripts/mode.sh status    # Show current mode
#   ./scripts/mode.sh interval  # Switch to interval mode (every 9 min)
#   ./scripts/mode.sh watcher   # Switch to watcher mode (hybrid triggers)
#   ./scripts/mode.sh stop      # Stop all modes
#

set -e

# ─────────────────────────────────────────────────────────────────────────────
# Configuration
# ─────────────────────────────────────────────────────────────────────────────

PLIST_DIR="$HOME/Library/LaunchAgents"
INTERVAL_PLIST="com.bss.email-nurse.plist"
WATCHER_PLIST="com.bss.email-nurse-watcher.plist"
INTERVAL_LABEL="com.bss.email-nurse"
WATCHER_LABEL="com.bss.email-nurse-watcher"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
DIM='\033[2m'
NC='\033[0m'

# ─────────────────────────────────────────────────────────────────────────────
# Helper Functions
# ─────────────────────────────────────────────────────────────────────────────

info() { echo "${CYAN}▶${NC} $1"; }
success() { echo "${GREEN}✓${NC} $1"; }
warn() { echo "${YELLOW}⚠${NC} $1"; }
error() { echo "${RED}✗${NC} $1"; exit 1; }

is_loaded() {
    local label="$1"
    launchctl list 2>/dev/null | grep -q "$label"
}

is_running() {
    local label="$1"
    local status=$(launchctl list 2>/dev/null | grep "$label" | awk '{print $1}')
    # Running if PID is a number (not "-" or exit code)
    [[ "$status" =~ ^[0-9]+$ ]]
}

get_watcher_pid() {
    pgrep -f "email-nurse autopilot watch" 2>/dev/null || echo ""
}

load_agent() {
    local plist="$1"
    local label="$2"

    if [[ ! -f "$PLIST_DIR/$plist" ]]; then
        error "Plist not found: $PLIST_DIR/$plist"
        echo "  Run: ${CYAN}./scripts/install.sh${NC} first"
        return 1
    fi

    if is_loaded "$label"; then
        info "Already loaded, restarting..."
        launchctl unload "$PLIST_DIR/$plist" 2>/dev/null || true
    fi

    launchctl load "$PLIST_DIR/$plist"
}

unload_agent() {
    local plist="$1"
    local label="$2"

    if is_loaded "$label"; then
        launchctl unload "$PLIST_DIR/$plist" 2>/dev/null || true
    fi
}

# ─────────────────────────────────────────────────────────────────────────────
# Commands
# ─────────────────────────────────────────────────────────────────────────────

cmd_status() {
    echo ""
    echo "${BOLD}${CYAN}═══════════════════════════════════════════════════════════${NC}"
    echo "${BOLD}           email-nurse Trigger Mode${NC}"
    echo "${BOLD}${CYAN}═══════════════════════════════════════════════════════════${NC}"
    echo ""

    local interval_loaded=$(is_loaded "$INTERVAL_LABEL" && echo "yes" || echo "no")
    local watcher_loaded=$(is_loaded "$WATCHER_LABEL" && echo "yes" || echo "no")
    local watcher_pid=$(get_watcher_pid)

    # Determine current mode
    local current_mode="none"

    if [[ -n "$watcher_pid" ]]; then
        current_mode="watcher"
        echo "  ${BOLD}Current Mode:${NC} ${GREEN}Watcher (Hybrid Triggers)${NC}"
        echo ""
        echo "  ${DIM}The watcher monitors your inbox continuously:${NC}"
        echo "  ${DIM}  - Polls every 30 seconds for new messages${NC}"
        echo "  ${DIM}  - Triggers immediately when new mail arrives${NC}"
        echo "  ${DIM}  - Full scan every 10 minutes${NC}"
        echo ""
        echo "  ${GREEN}●${NC} Watcher running (PID $watcher_pid)"
    elif [[ "$watcher_loaded" == "yes" ]]; then
        current_mode="watcher-idle"
        echo "  ${BOLD}Current Mode:${NC} ${YELLOW}Watcher (Idle)${NC}"
        echo ""
        if ! pgrep -xq "Mail"; then
            echo "  ${YELLOW}⚠${NC} Mail.app not running - watcher is waiting"
        else
            echo "  ${YELLOW}⚠${NC} Watcher loaded but not running (check logs)"
        fi
    elif [[ "$interval_loaded" == "yes" ]]; then
        current_mode="interval"
        echo "  ${BOLD}Current Mode:${NC} ${CYAN}Interval${NC}"
        echo ""
        echo "  ${DIM}Runs every 9 minutes when Mail.app is open${NC}"
        echo ""
        echo "  ${CYAN}●${NC} Interval agent loaded"
    else
        echo "  ${BOLD}Current Mode:${NC} ${RED}None${NC}"
        echo ""
        echo "  ${DIM}No trigger mode is active${NC}"
    fi

    echo ""
    echo "───────────────────────────────────────────────────────────"
    echo ""
    echo "  ${BOLD}Available Modes:${NC}"
    echo ""
    echo "  ${CYAN}interval${NC}  Runs every 9 minutes"
    echo "            Lower resource usage, batches emails"
    echo ""
    echo "  ${CYAN}watcher${NC}   Hybrid triggers (recommended)"
    echo "            Responds immediately to new emails"
    echo "            Polls inbox + scheduled scans"
    echo ""
    echo "  ${BOLD}Switch Mode:${NC} ${CYAN}./scripts/mode.sh [interval|watcher]${NC}"
    echo ""
}

cmd_interval() {
    echo ""
    info "Switching to Interval mode..."

    # Stop watcher if running
    if is_loaded "$WATCHER_LABEL"; then
        info "Stopping watcher..."
        unload_agent "$WATCHER_PLIST" "$WATCHER_LABEL"
        sleep 1
    fi

    # Start interval
    info "Starting interval agent..."
    load_agent "$INTERVAL_PLIST" "$INTERVAL_LABEL"

    echo ""
    success "Switched to ${BOLD}Interval Mode${NC}"
    echo "  Runs every 9 minutes when Mail.app is open"
    echo ""
}

cmd_watcher() {
    echo ""
    info "Switching to Watcher mode..."

    # Stop interval if running
    if is_loaded "$INTERVAL_LABEL"; then
        info "Stopping interval agent..."
        unload_agent "$INTERVAL_PLIST" "$INTERVAL_LABEL"
        sleep 1
    fi

    # Start watcher
    info "Starting watcher..."
    load_agent "$WATCHER_PLIST" "$WATCHER_LABEL"

    # Wait a moment for it to start
    sleep 2

    local watcher_pid=$(get_watcher_pid)
    if [[ -n "$watcher_pid" ]]; then
        echo ""
        success "Switched to ${BOLD}Watcher Mode${NC}"
        echo "  Running as PID $watcher_pid"
        echo "  Polls every 30s, triggers on new mail"
        echo ""
        echo "  View logs: ${CYAN}tail -f ~/Library/Logs/email-nurse-watcher.log${NC}"
    else
        echo ""
        warn "Watcher loaded but not running yet"
        if ! pgrep -xq "Mail"; then
            echo "  Mail.app is not running - watcher will start when it opens"
        else
            echo "  Check logs: ${CYAN}tail ~/Library/Logs/email-nurse-watcher-error.log${NC}"
        fi
    fi
    echo ""
}

cmd_stop() {
    echo ""
    info "Stopping all trigger modes..."

    if is_loaded "$WATCHER_LABEL"; then
        info "Stopping watcher..."
        unload_agent "$WATCHER_PLIST" "$WATCHER_LABEL"
    fi

    if is_loaded "$INTERVAL_LABEL"; then
        info "Stopping interval agent..."
        unload_agent "$INTERVAL_PLIST" "$INTERVAL_LABEL"
    fi

    echo ""
    success "All trigger modes stopped"
    echo "  Run ${CYAN}./scripts/mode.sh [interval|watcher]${NC} to restart"
    echo ""
}

cmd_restart() {
    echo ""
    info "Restarting current mode..."

    local watcher_pid=$(get_watcher_pid)

    if [[ -n "$watcher_pid" ]] || is_loaded "$WATCHER_LABEL"; then
        info "Restarting watcher..."
        unload_agent "$WATCHER_PLIST" "$WATCHER_LABEL"
        sleep 1
        load_agent "$WATCHER_PLIST" "$WATCHER_LABEL"
        sleep 2
        local new_pid=$(get_watcher_pid)
        if [[ -n "$new_pid" ]]; then
            success "Watcher restarted (PID $new_pid)"
        else
            warn "Watcher loaded but not running - check logs"
        fi
    elif is_loaded "$INTERVAL_LABEL"; then
        info "Restarting interval agent..."
        unload_agent "$INTERVAL_PLIST" "$INTERVAL_LABEL"
        sleep 1
        load_agent "$INTERVAL_PLIST" "$INTERVAL_LABEL"
        success "Interval agent restarted"
    else
        warn "No mode is currently active"
        echo "  Run ${CYAN}./scripts/mode.sh [interval|watcher]${NC} to start"
    fi
    echo ""
}

show_usage() {
    echo ""
    echo "${BOLD}Usage:${NC} $0 <command>"
    echo ""
    echo "${BOLD}Commands:${NC}"
    echo "  ${CYAN}status${NC}    Show current trigger mode"
    echo "  ${CYAN}interval${NC}  Switch to interval mode (runs every 9 min)"
    echo "  ${CYAN}watcher${NC}   Switch to watcher mode (hybrid triggers)"
    echo "  ${CYAN}stop${NC}      Stop all trigger modes"
    echo "  ${CYAN}restart${NC}   Restart the current mode"
    echo ""
}

# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

case "${1:-}" in
    status|"")
        cmd_status
        ;;
    interval)
        cmd_interval
        ;;
    watcher)
        cmd_watcher
        ;;
    stop)
        cmd_stop
        ;;
    restart)
        cmd_restart
        ;;
    *)
        show_usage
        exit 1
        ;;
esac
