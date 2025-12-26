#!/bin/zsh

# Log viewer for email-nurse
# Interactive menu to tail logs with Ctrl+C returning to menu

LOG_DIR="$HOME/Library/Logs"
MAIN_LOG="${LOG_DIR}/email-nurse.log"
ERROR_LOG="${LOG_DIR}/email-nurse-error.log"

# Colors
BOLD='\033[1m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
RED='\033[0;31m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

show_menu() {
    clear
    echo "${BOLD}${CYAN}═══════════════════════════════════════${NC}"
    echo "${BOLD}       Email Nurse Log Viewer${NC}"
    echo "${BOLD}${CYAN}═══════════════════════════════════════${NC}"
    echo ""
    echo "  ${GREEN}1)${NC} Tail main log      ${YELLOW}(email-nurse.log)${NC}"
    echo "  ${GREEN}2)${NC} Tail error log     ${YELLOW}(email-nurse-error.log)${NC}"
    echo "  ${GREEN}3)${NC} Tail both logs     ${YELLOW}(simultaneous)${NC}"
    echo "  ${RED}4)${NC} Quit"
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

    # tail -f with multiple files shows ==> filename <== headers
    tail -f "$MAIN_LOG" "$ERROR_LOG" 2>/dev/null
}

# Main loop
while true; do
    show_menu

    # Read single character
    echo -n "  Select option [1-4]: "
    read choice

    case "$choice" in
        1)
            # Trap Ctrl+C to break out of tail and return to menu
            trap 'echo ""; continue' INT
            tail_log "$MAIN_LOG" "main log"
            trap - INT
            ;;
        2)
            trap 'echo ""; continue' INT
            tail_log "$ERROR_LOG" "error log"
            trap - INT
            ;;
        3)
            trap 'echo ""; continue' INT
            tail_both
            trap - INT
            ;;
        4|q|Q)
            echo ""
            echo "${GREEN}Goodbye!${NC}"
            exit 0
            ;;
        *)
            echo "${RED}Invalid option${NC}"
            sleep 1
            ;;
    esac
done
