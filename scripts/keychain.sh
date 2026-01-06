#!/bin/zsh
#
# email-nurse keychain management
# Manage API keys in macOS Keychain
#
# Usage:
#   ./scripts/keychain.sh status   # Check which keys exist
#   ./scripts/keychain.sh add      # Interactive add
#   ./scripts/keychain.sh migrate  # Migrate from .env
#   ./scripts/keychain.sh remove   # Remove keys
#

set -e

# ─────────────────────────────────────────────────────────────────────────────
# Configuration
# ─────────────────────────────────────────────────────────────────────────────

CONFIG_DIR="$HOME/.config/email-nurse"
ENV_FILE="$CONFIG_DIR/.env"

# Keychain service names
ANTHROPIC_SERVICE="email-nurse-anthropic"
OPENAI_SERVICE="email-nurse-openai"

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
error() { echo "${RED}✗${NC} $1"; }

check_keychain() {
    local service="$1"
    security find-generic-password -a "$USER" -s "$service" -w >/dev/null 2>&1
}

get_keychain_key() {
    local service="$1"
    security find-generic-password -a "$USER" -s "$service" -w 2>/dev/null
}

set_keychain_key() {
    local service="$1"
    local key="$2"
    # -U flag updates if exists, otherwise creates
    security add-generic-password -a "$USER" -s "$service" -w "$key" -U 2>/dev/null
}

remove_keychain_key() {
    local service="$1"
    security delete-generic-password -a "$USER" -s "$service" 2>/dev/null
}

get_env_key() {
    local key_name="$1"
    if [[ -f "$ENV_FILE" ]]; then
        grep "^${key_name}=" "$ENV_FILE" 2>/dev/null | cut -d'=' -f2- | tr -d '"' | tr -d "'"
    fi
}

mask_key() {
    local key="$1"
    if [[ ${#key} -gt 12 ]]; then
        echo "${key:0:8}...${key: -4}"
    else
        echo "****"
    fi
}

# ─────────────────────────────────────────────────────────────────────────────
# Commands
# ─────────────────────────────────────────────────────────────────────────────

cmd_status() {
    echo ""
    echo "${BOLD}${CYAN}═══════════════════════════════════════════════════════════${NC}"
    echo "${BOLD}           email-nurse Keychain Status${NC}"
    echo "${BOLD}${CYAN}═══════════════════════════════════════════════════════════${NC}"
    echo ""

    # Check Anthropic key
    if check_keychain "$ANTHROPIC_SERVICE"; then
        local key=$(get_keychain_key "$ANTHROPIC_SERVICE")
        success "ANTHROPIC_API_KEY: $(mask_key "$key")"
    else
        error "ANTHROPIC_API_KEY: ${DIM}not found${NC}"

        # Check if in .env
        local env_key=$(get_env_key "ANTHROPIC_API_KEY")
        if [[ -n "$env_key" ]]; then
            warn "  Found in .env file - run '${CYAN}migrate${NC}' to move to Keychain"
        fi

        # Check environment variable
        if [[ -n "$ANTHROPIC_API_KEY" ]]; then
            warn "  Found in environment - run '${CYAN}migrate${NC}' to store in Keychain"
        fi
    fi

    # Check OpenAI key (optional)
    if check_keychain "$OPENAI_SERVICE"; then
        local key=$(get_keychain_key "$OPENAI_SERVICE")
        success "OPENAI_API_KEY: $(mask_key "$key") ${DIM}(optional)${NC}"
    else
        echo "${DIM}○${NC} OPENAI_API_KEY: ${DIM}not found (optional)${NC}"
    fi

    echo ""
}

cmd_add() {
    echo ""
    echo "${BOLD}${CYAN}═══════════════════════════════════════════════════════════${NC}"
    echo "${BOLD}           Add API Keys to Keychain${NC}"
    echo "${BOLD}${CYAN}═══════════════════════════════════════════════════════════${NC}"
    echo ""

    # Anthropic key
    if check_keychain "$ANTHROPIC_SERVICE"; then
        local existing=$(get_keychain_key "$ANTHROPIC_SERVICE")
        warn "ANTHROPIC_API_KEY already exists: $(mask_key "$existing")"
        read -q "REPLY?Overwrite? [y/N] "
        echo ""
        if [[ ! "$REPLY" =~ ^[Yy]$ ]]; then
            info "Keeping existing key"
        else
            echo -n "Enter Anthropic API key: "
            read -s api_key
            echo ""
            if [[ -n "$api_key" ]]; then
                set_keychain_key "$ANTHROPIC_SERVICE" "$api_key"
                success "ANTHROPIC_API_KEY updated"
            fi
        fi
    else
        echo -n "Enter Anthropic API key (sk-ant-...): "
        read -s api_key
        echo ""
        if [[ -n "$api_key" ]]; then
            set_keychain_key "$ANTHROPIC_SERVICE" "$api_key"
            success "ANTHROPIC_API_KEY stored in Keychain"
        else
            warn "No key provided, skipping"
        fi
    fi

    echo ""

    # OpenAI key (optional)
    read -q "REPLY?Add OpenAI API key? (optional) [y/N] "
    echo ""
    if [[ "$REPLY" =~ ^[Yy]$ ]]; then
        echo -n "Enter OpenAI API key (sk-...): "
        read -s api_key
        echo ""
        if [[ -n "$api_key" ]]; then
            set_keychain_key "$OPENAI_SERVICE" "$api_key"
            success "OPENAI_API_KEY stored in Keychain"
        fi
    fi

    echo ""
    info "Done! Run 'status' to verify."
    echo ""
}

cmd_migrate() {
    echo ""
    echo "${BOLD}${CYAN}═══════════════════════════════════════════════════════════${NC}"
    echo "${BOLD}           Migrate API Keys to Keychain${NC}"
    echo "${BOLD}${CYAN}═══════════════════════════════════════════════════════════${NC}"
    echo ""

    local migrated=0
    local anthropic_source=""
    local anthropic_key=""

    # Find Anthropic key from various sources
    if ! check_keychain "$ANTHROPIC_SERVICE"; then
        # Try .env file first
        anthropic_key=$(get_env_key "ANTHROPIC_API_KEY")
        if [[ -n "$anthropic_key" ]]; then
            anthropic_source=".env file"
        fi

        # Try environment variable
        if [[ -z "$anthropic_key" && -n "$ANTHROPIC_API_KEY" ]]; then
            anthropic_key="$ANTHROPIC_API_KEY"
            anthropic_source="environment variable"
        fi

        # Try project .env
        if [[ -z "$anthropic_key" && -f ".env" ]]; then
            anthropic_key=$(grep "^ANTHROPIC_API_KEY=" ".env" 2>/dev/null | cut -d'=' -f2- | tr -d '"' | tr -d "'")
            if [[ -n "$anthropic_key" ]]; then
                anthropic_source="project .env"
            fi
        fi

        if [[ -n "$anthropic_key" ]]; then
            info "Found ANTHROPIC_API_KEY in $anthropic_source: $(mask_key "$anthropic_key")"
            read -q "REPLY?Migrate to Keychain? [Y/n] "
            echo ""
            if [[ ! "$REPLY" =~ ^[Nn]$ ]]; then
                set_keychain_key "$ANTHROPIC_SERVICE" "$anthropic_key"
                success "ANTHROPIC_API_KEY migrated to Keychain"
                migrated=$((migrated + 1))

                # Offer to remove from .env
                if [[ "$anthropic_source" == ".env file" ]]; then
                    read -q "REPLY?Remove from $ENV_FILE? (recommended for security) [Y/n] "
                    echo ""
                    if [[ ! "$REPLY" =~ ^[Nn]$ ]]; then
                        sed -i '' '/^ANTHROPIC_API_KEY=/d' "$ENV_FILE"
                        success "Removed from $ENV_FILE"
                    fi
                fi
            fi
        else
            warn "No ANTHROPIC_API_KEY found to migrate"
            echo "  Checked: .env file, environment variable, project .env"
        fi
    else
        success "ANTHROPIC_API_KEY already in Keychain"
    fi

    echo ""

    # OpenAI key migration (similar logic)
    if ! check_keychain "$OPENAI_SERVICE"; then
        local openai_key=""
        local openai_source=""

        openai_key=$(get_env_key "OPENAI_API_KEY")
        if [[ -n "$openai_key" ]]; then
            openai_source=".env file"
        elif [[ -n "$OPENAI_API_KEY" ]]; then
            openai_key="$OPENAI_API_KEY"
            openai_source="environment variable"
        fi

        if [[ -n "$openai_key" ]]; then
            info "Found OPENAI_API_KEY in $openai_source: $(mask_key "$openai_key")"
            read -q "REPLY?Migrate to Keychain? [Y/n] "
            echo ""
            if [[ ! "$REPLY" =~ ^[Nn]$ ]]; then
                set_keychain_key "$OPENAI_SERVICE" "$openai_key"
                success "OPENAI_API_KEY migrated to Keychain"
                migrated=$((migrated + 1))
            fi
        fi
    fi

    echo ""
    if [[ $migrated -gt 0 ]]; then
        success "Migration complete! $migrated key(s) migrated."
    else
        info "No keys needed migration."
    fi
    echo ""
}

cmd_remove() {
    echo ""
    echo "${BOLD}${CYAN}═══════════════════════════════════════════════════════════${NC}"
    echo "${BOLD}           Remove API Keys from Keychain${NC}"
    echo "${BOLD}${CYAN}═══════════════════════════════════════════════════════════${NC}"
    echo ""

    warn "This will remove API keys from Keychain."
    echo ""

    if check_keychain "$ANTHROPIC_SERVICE"; then
        read -q "REPLY?Remove ANTHROPIC_API_KEY? [y/N] "
        echo ""
        if [[ "$REPLY" =~ ^[Yy]$ ]]; then
            remove_keychain_key "$ANTHROPIC_SERVICE"
            success "ANTHROPIC_API_KEY removed"
        fi
    else
        info "ANTHROPIC_API_KEY not in Keychain"
    fi

    if check_keychain "$OPENAI_SERVICE"; then
        read -q "REPLY?Remove OPENAI_API_KEY? [y/N] "
        echo ""
        if [[ "$REPLY" =~ ^[Yy]$ ]]; then
            remove_keychain_key "$OPENAI_SERVICE"
            success "OPENAI_API_KEY removed"
        fi
    else
        info "OPENAI_API_KEY not in Keychain"
    fi

    echo ""
}

show_usage() {
    echo ""
    echo "${BOLD}Usage:${NC} $0 <command>"
    echo ""
    echo "${BOLD}Commands:${NC}"
    echo "  ${CYAN}status${NC}   Check which API keys are in Keychain"
    echo "  ${CYAN}add${NC}      Interactively add API keys"
    echo "  ${CYAN}migrate${NC}  Migrate keys from .env or environment to Keychain"
    echo "  ${CYAN}remove${NC}   Remove API keys from Keychain"
    echo ""
}

# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

case "${1:-}" in
    status)
        cmd_status
        ;;
    add)
        cmd_add
        ;;
    migrate)
        cmd_migrate
        ;;
    remove)
        cmd_remove
        ;;
    *)
        show_usage
        exit 1
        ;;
esac
