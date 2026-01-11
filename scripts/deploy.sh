#!/bin/bash
# deploy.sh - Deploy email-nurse to a remote macOS host via SSH
#
# Usage: ./scripts/deploy.sh <ssh-host> [options]
#        ./scripts/deploy.sh --snapshot
#
# Options:
#   --dry-run     Show what would be transferred without doing it
#   --force       Overwrite existing installation
#   --no-agent    Skip LaunchAgent installation
#   --config-only Transfer config files only (for updates)
#   --snapshot    Backup current production configs to deploy/ directory
#
set -euo pipefail

# Get script directory (for finding deploy/ folder)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(dirname "$SCRIPT_DIR")"
DEPLOY_DIR="$REPO_DIR/deploy"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
BOLD='\033[1m'
NC='\033[0m' # No Color

# Paths (relative to home directory)
APP_DIR=".local/share/email-nurse"
BIN_DIR=".local/bin"
CONFIG_DIR=".config/email-nurse"
LAUNCH_AGENT_DIR="Library/LaunchAgents"
LAUNCH_AGENT_NAME="com.bss.email-nurse.plist"
KEYCHAIN_SERVICE="email-nurse-anthropic"
LOG_DIR="Library/Logs"

# Default options
DRY_RUN=false
FORCE=false
NO_AGENT=false
CONFIG_ONLY=false
SNAPSHOT=false
RESTART_ONLY=false

usage() {
    cat << EOF
${BOLD}Email-Nurse Remote Deployment${NC}

Usage: $0 <ssh-host> [options]
       $0 --snapshot

Arguments:
  ssh-host        SSH destination (e.g., hostname, user@host, or SSH config alias)

Options:
  --dry-run       Show what would be transferred without doing it
  --force         Overwrite existing installation without prompting
  --no-agent      Skip LaunchAgent installation
  --config-only   Transfer config files only (useful for updates)
  --restart       Restart the LaunchAgent only (no file transfers)
  --snapshot      Backup current production configs to deploy/ directory
  -h, --help      Show this help message

Examples:
  $0 --snapshot                  # Backup production configs first
  $0 myserver                    # Full deployment to 'myserver'
  $0 user@192.168.1.100          # Deploy to specific host
  $0 myserver --config-only      # Update config only
  $0 myserver --restart          # Restart service without deploying
  $0 myserver --dry-run          # Preview what would happen

Config Sources (checked in order):
  1. $DEPLOY_DIR/  (local backup, gitignored)
  2. ~/.config/email-nurse/           (production location)
EOF
    exit 0
}

# Snapshot function - backup production configs to deploy/
do_snapshot() {
    echo -e "${BOLD}Snapshotting Production Configs${NC}"
    echo "================================"
    echo ""

    mkdir -p "$DEPLOY_DIR"/{config,bin,launchagent}

    # Config files (including dotfiles)
    echo -n "Config files... "
    if [[ -d ~/.config/email-nurse ]]; then
        # Use rsync to properly copy all files including dotfiles
        rsync -a ~/.config/email-nurse/ "$DEPLOY_DIR/config/"
        echo -e "${GREEN}OK${NC}"
        ls -la "$DEPLOY_DIR/config/" | tail -n +2
    else
        echo -e "${YELLOW}not found${NC}"
    fi
    echo ""

    # Launcher scripts
    echo -n "Launcher scripts... "
    if ls ~/.local/bin/email-nurse-*.sh >/dev/null 2>&1; then
        cp ~/.local/bin/email-nurse-*.sh "$DEPLOY_DIR/bin/" 2>/dev/null || true
        echo -e "${GREEN}OK${NC}"
        ls -la "$DEPLOY_DIR/bin/" | tail -n +2
    else
        echo -e "${YELLOW}not found${NC}"
    fi
    echo ""

    # LaunchAgent
    echo -n "LaunchAgent plist... "
    if [[ -f ~/Library/LaunchAgents/$LAUNCH_AGENT_NAME ]]; then
        cp ~/Library/LaunchAgents/$LAUNCH_AGENT_NAME "$DEPLOY_DIR/launchagent/" 2>/dev/null || true
        echo -e "${GREEN}OK${NC}"
        ls -la "$DEPLOY_DIR/launchagent/" | tail -n +2
    else
        echo -e "${YELLOW}not found${NC}"
    fi
    echo ""

    # Summary
    echo -e "${GREEN}Snapshot complete!${NC}"
    echo ""
    echo "Saved to: $DEPLOY_DIR/"
    echo ""
    echo "Contents:"
    du -sh "$DEPLOY_DIR"/* 2>/dev/null | sed 's/^/  /'
    echo ""
    echo -e "${YELLOW}Note:${NC} This directory is gitignored and won't sync to remote repo."
    echo "API keys are stored in macOS Keychain, not in these files."
    exit 0
}

log_step() {
    local step=$1
    local total=$2
    local msg=$3
    echo -e "${BLUE}[$step/$total]${NC} $msg"
}

log_ok() {
    echo -e "${GREEN}OK${NC}"
}

log_skip() {
    echo -e "${YELLOW}SKIPPED${NC}"
}

log_fail() {
    echo -e "${RED}FAILED${NC}"
}

log_info() {
    echo -e "      $1"
}

die() {
    echo -e "${RED}Error:${NC} $1" >&2
    exit 1
}

# Restart the LaunchAgent on remote host (legacy, for --restart flag)
restart_agent() {
    echo -n "Restarting LaunchAgent..."
    if ssh "$TARGET_HOST" "launchctl stop com.bss.email-nurse 2>/dev/null; launchctl start com.bss.email-nurse"; then
        log_ok
        return 0
    else
        log_fail
        return 1
    fi
}

# Restart the watcher service on remote host (proper restart sequence)
restart_watcher() {
    local install_dir="$APP_DIR/current"
    local service="com.bss.email-nurse-watcher"

    echo -n "      Stopping watcher process..."
    ssh "$TARGET_HOST" "pkill -f 'email-nurse autopilot watch' 2>/dev/null || true"
    sleep 2
    log_ok

    echo -n "      Clearing stale PID lock..."
    ssh "$TARGET_HOST" "~/$install_dir/venv/bin/email-nurse autopilot reset-watcher 2>/dev/null || true"
    log_ok

    echo -n "      Starting watcher service..."
    if ssh "$TARGET_HOST" "launchctl start '$service'" 2>/dev/null; then
        sleep 3
        log_ok
    else
        log_fail
        return 1
    fi

    # Verify
    echo -n "      Verifying watcher..."
    local pid
    pid=$(ssh "$TARGET_HOST" "pgrep -f 'email-nurse autopilot watch' 2>/dev/null || true")
    if [[ -n "$pid" ]]; then
        log_ok
        log_info "Watcher running (PID $pid)"
        return 0
    else
        log_fail
        log_info "Check logs: ssh $TARGET_HOST 'tail ~/Library/Logs/email-nurse-watcher-error.log'"
        return 1
    fi
}

# Parse arguments
TARGET_HOST=""
while [[ $# -gt 0 ]]; do
    case $1 in
        --dry-run)
            DRY_RUN=true
            shift
            ;;
        --force)
            FORCE=true
            shift
            ;;
        --no-agent)
            NO_AGENT=true
            shift
            ;;
        --config-only)
            CONFIG_ONLY=true
            shift
            ;;
        --snapshot)
            SNAPSHOT=true
            shift
            ;;
        --restart)
            RESTART_ONLY=true
            shift
            ;;
        -h|--help)
            usage
            ;;
        -*)
            die "Unknown option: $1"
            ;;
        *)
            if [[ -z "$TARGET_HOST" ]]; then
                TARGET_HOST="$1"
            else
                die "Unexpected argument: $1"
            fi
            shift
            ;;
    esac
done

# Handle snapshot mode (doesn't require target host)
if $SNAPSHOT; then
    do_snapshot
fi

[[ -z "$TARGET_HOST" ]] && die "SSH host is required. Use -h for help."

# Handle restart-only mode
if $RESTART_ONLY; then
    echo ""
    echo -e "${BOLD}Restarting Email-Nurse on $TARGET_HOST${NC}"
    echo ""

    # Check SSH connectivity
    echo -n "Checking SSH connectivity..."
    if ! ssh -o ConnectTimeout=10 -o BatchMode=yes "$TARGET_HOST" 'true' 2>/dev/null; then
        log_fail
        die "Cannot connect to $TARGET_HOST"
    fi
    log_ok

    # Restart the agent
    restart_agent

    # Verify
    echo ""
    AGENT_STATUS=$(ssh "$TARGET_HOST" "launchctl list 2>/dev/null | grep -E 'com\.bss\.email-nurse\s' | awk '{print \$1}'")
    if [[ -n "$AGENT_STATUS" && "$AGENT_STATUS" != "-" ]]; then
        echo -e "${GREEN}✓${NC} LaunchAgent running (PID: $AGENT_STATUS)"
    else
        echo -e "${GREEN}✓${NC} LaunchAgent restarted (waiting for next run)"
    fi
    exit 0
fi

# Determine config source (prefer deploy/ if it exists)
if [[ -d "$DEPLOY_DIR/config" ]] && [[ -n "$(ls -A "$DEPLOY_DIR/config" 2>/dev/null)" ]]; then
    CONFIG_SOURCE="$DEPLOY_DIR/config"
    CONFIG_SOURCE_LABEL="deploy/ (local backup)"
else
    CONFIG_SOURCE="$HOME/$CONFIG_DIR"
    CONFIG_SOURCE_LABEL="~/$CONFIG_DIR (production)"
fi

# Determine scripts source
if [[ -d "$DEPLOY_DIR/bin" ]] && [[ -n "$(ls -A "$DEPLOY_DIR/bin" 2>/dev/null)" ]]; then
    BIN_SOURCE="$DEPLOY_DIR/bin"
else
    BIN_SOURCE="$HOME/$BIN_DIR"
fi

# Determine LaunchAgent source
if [[ -f "$DEPLOY_DIR/launchagent/$LAUNCH_AGENT_NAME" ]]; then
    LAUNCHAGENT_SOURCE="$DEPLOY_DIR/launchagent/$LAUNCH_AGENT_NAME"
else
    LAUNCHAGENT_SOURCE="$HOME/$LAUNCH_AGENT_DIR/$LAUNCH_AGENT_NAME"
fi

# Header
echo ""
echo -e "${BOLD}Email-Nurse Remote Deployment${NC}"
echo "=============================="
echo -e "Target: ${BOLD}$TARGET_HOST${NC}"
echo -e "Config: ${CONFIG_SOURCE_LABEL}"
if $DRY_RUN; then
    echo -e "${YELLOW}(dry-run mode - no changes will be made)${NC}"
fi
echo ""

TOTAL_STEPS=9
if $CONFIG_ONLY; then
    TOTAL_STEPS=5
fi

# Step 1: Check SSH connectivity
log_step 1 $TOTAL_STEPS "Checking SSH connectivity..."
if ! ssh -o ConnectTimeout=10 -o BatchMode=yes "$TARGET_HOST" 'true' 2>/dev/null; then
    log_fail
    die "Cannot connect to $TARGET_HOST. Check SSH config and connectivity."
fi
log_ok

# Step 2: Verify remote environment
log_step 2 $TOTAL_STEPS "Verifying remote environment..."
REMOTE_INFO=$(ssh "$TARGET_HOST" 'echo "$(uname -s)|$(uname -m)|$(pgrep -x Mail >/dev/null && echo running || echo stopped)"')
REMOTE_OS=$(echo "$REMOTE_INFO" | cut -d'|' -f1)
REMOTE_ARCH=$(echo "$REMOTE_INFO" | cut -d'|' -f2)
REMOTE_MAIL=$(echo "$REMOTE_INFO" | cut -d'|' -f3)

log_ok
log_info "- OS: $REMOTE_OS"
log_info "- Arch: $REMOTE_ARCH"
log_info "- Mail.app: $REMOTE_MAIL"

# Validate environment
if [[ "$REMOTE_OS" != "Darwin" ]]; then
    die "Remote host is not macOS (got: $REMOTE_OS)"
fi

LOCAL_ARCH=$(uname -m)
if [[ "$REMOTE_ARCH" != "$LOCAL_ARCH" ]]; then
    die "Architecture mismatch: local=$LOCAL_ARCH, remote=$REMOTE_ARCH. Cannot transfer venv."
fi

if [[ "$REMOTE_MAIL" != "running" ]]; then
    echo -e "${YELLOW}Warning:${NC} Mail.app is not running on remote. LaunchAgent will skip processing until Mail.app starts."
fi

# Check for existing installation
EXISTING=$(ssh "$TARGET_HOST" "[[ -d ~/$APP_DIR ]] && echo yes || echo no")
if [[ "$EXISTING" == "yes" ]] && ! $FORCE && ! $CONFIG_ONLY; then
    echo ""
    echo -e "${YELLOW}Existing installation found on $TARGET_HOST${NC}"
    read -p "Overwrite? [y/N] " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo "Aborted."
        exit 0
    fi
fi

if $CONFIG_ONLY; then
    # Config-only mode: just transfer config files
    log_step 3 $TOTAL_STEPS "Transferring configuration from ${CONFIG_SOURCE_LABEL}..."
    if $DRY_RUN; then
        rsync -avzn --progress "$CONFIG_SOURCE"/ "$TARGET_HOST":~/"$CONFIG_DIR"/
    else
        rsync -avz --progress "$CONFIG_SOURCE"/ "$TARGET_HOST":~/"$CONFIG_DIR"/
    fi
    log_ok

    log_step 4 $TOTAL_STEPS "Verifying configuration..."
    ssh "$TARGET_HOST" "ls -la ~/$CONFIG_DIR/" | head -10
    log_ok

    # Restart to apply changes
    if ! $DRY_RUN; then
        log_step 5 $TOTAL_STEPS "Restarting LaunchAgent..."
        restart_agent
    else
        log_step 5 $TOTAL_STEPS "Restarting LaunchAgent..."
        log_skip
        log_info "(dry-run mode)"
    fi

    echo ""
    echo -e "${GREEN}Configuration updated and service restarted!${NC}"
    exit 0
fi

# Step 3: Install uv if needed
log_step 3 $TOTAL_STEPS "Checking uv package manager..."
HAS_UV=$(ssh "$TARGET_HOST" 'command -v uv >/dev/null && echo yes || echo no')
if [[ "$HAS_UV" == "no" ]]; then
    echo -n " installing..."
    if ! $DRY_RUN; then
        ssh "$TARGET_HOST" 'curl -LsSf https://astral.sh/uv/install.sh | sh' >/dev/null 2>&1
    fi
fi
log_ok

# Step 4: Create directories
log_step 4 $TOTAL_STEPS "Creating directories..."
if ! $DRY_RUN; then
    ssh "$TARGET_HOST" "mkdir -p ~/$BIN_DIR ~/$APP_DIR ~/$CONFIG_DIR ~/$LAUNCH_AGENT_DIR ~/.local/state/email-nurse"
fi
log_ok

# Step 5: Transfer source and build application
log_step 5 $TOTAL_STEPS "Transferring source code..."
if $DRY_RUN; then
    rsync -avzn --progress --exclude '.venv' --exclude '__pycache__' --exclude '*.pyc' \
        --exclude '.git' --exclude 'deploy' \
        "$REPO_DIR"/ "$TARGET_HOST":~/.local/src/email-nurse/
else
    ssh "$TARGET_HOST" "mkdir -p ~/.local/src"
    rsync -avz --progress --exclude '.venv' --exclude '__pycache__' --exclude '*.pyc' \
        --exclude '.git' --exclude 'deploy' \
        "$REPO_DIR"/ "$TARGET_HOST":~/.local/src/email-nurse/
fi
log_ok

# Step 5b: Build venv on remote
echo -n "      Building application on remote..."
if ! $DRY_RUN; then
    ssh "$TARGET_HOST" 'cd ~/.local/src/email-nurse && \
        export PATH="$HOME/.local/bin:$PATH" && \
        uv venv ~/.local/share/email-nurse/versions/remote/venv --python 3.12 && \
        source ~/.local/share/email-nurse/versions/remote/venv/bin/activate && \
        uv pip install -e . && \
        rm -f ~/.local/share/email-nurse/current && \
        ln -s ~/.local/share/email-nurse/versions/remote ~/.local/share/email-nurse/current && \
        echo "remote" > ~/.local/share/email-nurse/versions/remote/VERSION'
fi
log_ok

# Step 5c: Transfer launcher scripts
echo -n "      Transferring launcher scripts..."
if $DRY_RUN; then
    rsync -avzn "$BIN_SOURCE"/email-nurse-*.sh "$TARGET_HOST":~/"$BIN_DIR"/ 2>/dev/null || true
else
    rsync -avz "$BIN_SOURCE"/email-nurse-*.sh "$TARGET_HOST":~/"$BIN_DIR"/ 2>/dev/null || true
    ssh "$TARGET_HOST" "chmod +x ~/$BIN_DIR/email-nurse-*.sh 2>/dev/null" || true
fi
log_ok

# Step 6: Transfer configuration
log_step 6 $TOTAL_STEPS "Transferring configuration from ${CONFIG_SOURCE_LABEL}..."
if $DRY_RUN; then
    rsync -avzn --progress "$CONFIG_SOURCE"/ "$TARGET_HOST":~/"$CONFIG_DIR"/
else
    rsync -avz --progress "$CONFIG_SOURCE"/ "$TARGET_HOST":~/"$CONFIG_DIR"/
fi
log_ok

# Step 7: Setup Keychain secret
log_step 7 $TOTAL_STEPS "Setting up Keychain secret..."
# Check if local keychain has the secret
if ! security find-generic-password -s "$KEYCHAIN_SERVICE" >/dev/null 2>&1; then
    echo -e "${YELLOW}SKIPPED${NC} (no local key found)"
    KEYCHAIN_NEEDS_SETUP=true
else
    # Check if remote already has the key
    REMOTE_HAS_KEY=$(ssh "$TARGET_HOST" "security find-generic-password -s '$KEYCHAIN_SERVICE' >/dev/null 2>&1 && echo yes || echo no")
    if [[ "$REMOTE_HAS_KEY" == "yes" ]] && ! $FORCE; then
        log_skip
        log_info "(key already exists on remote)"
        KEYCHAIN_NEEDS_SETUP=false
    else
        if ! $DRY_RUN; then
            # Delete existing if force mode
            if [[ "$REMOTE_HAS_KEY" == "yes" ]]; then
                ssh "$TARGET_HOST" "security delete-generic-password -s '$KEYCHAIN_SERVICE'" >/dev/null 2>&1 || true
            fi
            # Transfer the key securely - NOTE: This may fail due to macOS security (requires local user)
            API_KEY=$(security find-generic-password -s "$KEYCHAIN_SERVICE" -w 2>/dev/null)
            if ssh "$TARGET_HOST" "security add-generic-password -a \"\$USER\" -s '$KEYCHAIN_SERVICE' -w '$API_KEY'" 2>/dev/null; then
                log_ok
                KEYCHAIN_NEEDS_SETUP=false
            else
                echo -e "${YELLOW}MANUAL SETUP REQUIRED${NC}"
                log_info "macOS requires local user interaction for Keychain writes."
                KEYCHAIN_NEEDS_SETUP=true
            fi
        else
            log_ok
            KEYCHAIN_NEEDS_SETUP=false
        fi
    fi
fi

# Step 8: Install LaunchAgent
if $NO_AGENT; then
    log_step 8 $TOTAL_STEPS "Installing LaunchAgent..."
    log_skip
    log_info "(--no-agent flag set)"
else
    log_step 8 $TOTAL_STEPS "Installing LaunchAgent..."
    if ! $DRY_RUN; then
        # Unload existing if present
        ssh "$TARGET_HOST" "launchctl unload ~/$LAUNCH_AGENT_DIR/$LAUNCH_AGENT_NAME 2>/dev/null" || true

        # Copy plist from determined source
        scp "$LAUNCHAGENT_SOURCE" "$TARGET_HOST":~/"$LAUNCH_AGENT_DIR/" >/dev/null

        # Load and start agent
        ssh "$TARGET_HOST" "launchctl load ~/$LAUNCH_AGENT_DIR/$LAUNCH_AGENT_NAME && launchctl start com.bss.email-nurse"
    fi
    log_ok
fi

# Step 9: Restart watcher service
if $NO_AGENT; then
    log_step 9 $TOTAL_STEPS "Restarting watcher service..."
    log_skip
    log_info "(--no-agent flag set)"
else
    log_step 9 $TOTAL_STEPS "Restarting watcher service..."
    if ! $DRY_RUN; then
        restart_watcher
    else
        log_skip
        log_info "(dry-run mode)"
    fi
fi

# Verification
echo ""
echo -e "${BOLD}Verification${NC}"
echo "------------"

if $DRY_RUN; then
    echo "(skipped in dry-run mode)"
else
    # Check version
    VERSION=$(ssh "$TARGET_HOST" "~/$APP_DIR/current/venv/bin/email-nurse version 2>/dev/null" | head -1 || echo "unknown")
    echo -e "${GREEN}✓${NC} email-nurse version: $VERSION"

    # Check LaunchAgent
    if ! $NO_AGENT; then
        AGENT_STATUS=$(ssh "$TARGET_HOST" "launchctl list | grep -q com.bss.email-nurse && echo loaded || echo not_loaded")
        if [[ "$AGENT_STATUS" == "loaded" ]]; then
            echo -e "${GREEN}✓${NC} LaunchAgent: loaded"
        else
            echo -e "${YELLOW}!${NC} LaunchAgent: not loaded"
        fi
    fi

    # Check Keychain
    KEYCHAIN_OK=$(ssh "$TARGET_HOST" "security find-generic-password -s '$KEYCHAIN_SERVICE' >/dev/null 2>&1 && echo ok || echo missing")
    if [[ "$KEYCHAIN_OK" == "ok" ]]; then
        echo -e "${GREEN}✓${NC} Keychain secret: configured"
    else
        echo -e "${YELLOW}!${NC} Keychain secret: missing (autopilot will fail)"
    fi
fi

echo ""
if [[ "${KEYCHAIN_NEEDS_SETUP:-false}" == "true" ]]; then
    echo -e "${YELLOW}Deployment complete - Keychain setup required!${NC}"
    echo ""
    echo -e "${BOLD}To complete setup, run this on the remote machine:${NC}"
    echo ""
    echo "  1. SSH to remote:  ssh $TARGET_HOST"
    echo "  2. Add API key:    security add-generic-password -a \"\$USER\" -s \"$KEYCHAIN_SERVICE\" -w \"YOUR_ANTHROPIC_API_KEY\""
    echo ""
else
    echo -e "${GREEN}Deployment complete!${NC}"
fi
echo ""
echo "Monitor with:"
echo "  ssh $TARGET_HOST 'tail -f ~/Library/Logs/email-nurse.log'"
echo ""
echo "Manual run:"
echo "  ssh $TARGET_HOST '~/.local/bin/email-nurse-autopilot.sh'"
