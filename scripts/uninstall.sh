#!/bin/zsh
#
# email-nurse uninstall script
# Removes email-nurse system installation
#
# Usage:
#   ./scripts/uninstall.sh           # Interactive uninstall
#   ./scripts/uninstall.sh --full    # Remove everything including config
#

set -e

# ─────────────────────────────────────────────────────────────────────────────
# Configuration
# ─────────────────────────────────────────────────────────────────────────────

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

confirm() {
    local prompt="$1"
    read -q "REPLY?$prompt [y/N] "
    echo ""
    [[ "$REPLY" =~ ^[Yy]$ ]]
}

# ─────────────────────────────────────────────────────────────────────────────
# Main Uninstall
# ─────────────────────────────────────────────────────────────────────────────

echo ""
echo "${BOLD}${RED}═══════════════════════════════════════════════════════════${NC}"
echo "${BOLD}           email-nurse Uninstall${NC}"
echo "${BOLD}${RED}═══════════════════════════════════════════════════════════${NC}"
echo ""

FULL_UNINSTALL=false
if [[ "$1" == "--full" ]]; then
    FULL_UNINSTALL=true
    warn "Full uninstall requested (includes config and logs)"
fi

# Show what will be removed
echo "${BOLD}The following will be removed:${NC}"
echo ""
echo "  ${CYAN}Core Installation:${NC}"
[[ -d "$INSTALL_BASE" ]] && echo "    • $INSTALL_BASE"
[[ -f "$BIN_DIR/email-nurse-autopilot.sh" ]] && echo "    • $BIN_DIR/email-nurse-autopilot.sh"
[[ -f "$BIN_DIR/email-nurse-logs.sh" ]] && echo "    • $BIN_DIR/email-nurse-logs.sh"
[[ -d "$STATE_DIR" ]] && echo "    • $STATE_DIR"
[[ -f "$PLIST_DIR/$PLIST_NAME" ]] && echo "    • $PLIST_DIR/$PLIST_NAME (LaunchAgent)"

if [[ "$FULL_UNINSTALL" == "true" ]]; then
    echo ""
    echo "  ${YELLOW}Also removing (--full):${NC}"
    [[ -d "$CONFIG_DIR" ]] && echo "    • $CONFIG_DIR (configuration)"
    echo "    • $LOG_DIR/email-nurse*.log (logs)"
    echo "    • Keychain entries (API keys)"
fi

echo ""

if ! confirm "Proceed with uninstall?"; then
    echo "Cancelled."
    exit 0
fi

echo ""

# ─────────────────────────────────────────────────────────────────────────────
# Step 1: Unload LaunchAgent
# ─────────────────────────────────────────────────────────────────────────────

if [[ -f "$PLIST_DIR/$PLIST_NAME" ]]; then
    info "Unloading LaunchAgent..."
    launchctl unload "$PLIST_DIR/$PLIST_NAME" 2>/dev/null || true
    rm -f "$PLIST_DIR/$PLIST_NAME"
    success "LaunchAgent removed"
else
    info "LaunchAgent not found, skipping"
fi

# ─────────────────────────────────────────────────────────────────────────────
# Step 2: Remove Launch Scripts
# ─────────────────────────────────────────────────────────────────────────────

info "Removing launch scripts..."
rm -f "$BIN_DIR/email-nurse-autopilot.sh"
rm -f "$BIN_DIR/email-nurse-logs.sh"
success "Launch scripts removed"

# ─────────────────────────────────────────────────────────────────────────────
# Step 3: Remove Installation Directory
# ─────────────────────────────────────────────────────────────────────────────

if [[ -d "$INSTALL_BASE" ]]; then
    info "Removing installation directory..."
    rm -rf "$INSTALL_BASE"
    success "Installation removed: $INSTALL_BASE"
fi

# ─────────────────────────────────────────────────────────────────────────────
# Step 4: Remove State Directory
# ─────────────────────────────────────────────────────────────────────────────

if [[ -d "$STATE_DIR" ]]; then
    info "Removing state directory..."
    rm -rf "$STATE_DIR"
    success "State removed: $STATE_DIR"
fi

# ─────────────────────────────────────────────────────────────────────────────
# Step 5: Full Uninstall (Optional)
# ─────────────────────────────────────────────────────────────────────────────

if [[ "$FULL_UNINSTALL" == "true" ]]; then
    # Config
    if [[ -d "$CONFIG_DIR" ]]; then
        info "Removing configuration..."
        rm -rf "$CONFIG_DIR"
        success "Configuration removed: $CONFIG_DIR"
    fi

    # Logs
    info "Removing log files..."
    rm -f "$LOG_DIR/email-nurse.log"
    rm -f "$LOG_DIR/email-nurse-error.log"
    success "Log files removed"

    # Keychain
    info "Removing Keychain entries..."
    security delete-generic-password -a "$USER" -s "email-nurse-anthropic" 2>/dev/null && \
        success "Removed: email-nurse-anthropic" || \
        info "No Anthropic key found"
    security delete-generic-password -a "$USER" -s "email-nurse-openai" 2>/dev/null && \
        success "Removed: email-nurse-openai" || \
        info "No OpenAI key found"
fi

# ─────────────────────────────────────────────────────────────────────────────
# Done!
# ─────────────────────────────────────────────────────────────────────────────

echo ""
echo "${BOLD}${GREEN}═══════════════════════════════════════════════════════════${NC}"
echo "${BOLD}${GREEN}           Uninstall Complete!${NC}"
echo "${BOLD}${GREEN}═══════════════════════════════════════════════════════════${NC}"
echo ""

if [[ "$FULL_UNINSTALL" == "false" ]]; then
    echo "  ${YELLOW}The following were preserved:${NC}"
    [[ -d "$CONFIG_DIR" ]] && echo "    • $CONFIG_DIR (configuration)"
    echo "    • $LOG_DIR/email-nurse*.log (logs)"
    echo "    • Keychain entries (API keys)"
    echo ""
    echo "  To remove everything, run:"
    echo "    ${CYAN}./scripts/uninstall.sh --full${NC}"
    echo ""
fi

echo "  To reinstall, run:"
echo "    ${CYAN}./scripts/install.sh${NC}"
echo ""
