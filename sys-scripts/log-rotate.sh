#!/bin/zsh

# log-rotate.sh
# Rotate shell-managed logs that aren't handled by Python's RotatingFileHandler.
# Checks file size > 5MB, keeps 3 backups (.1, .2, .3).

set -o pipefail

LOG_DIR="$HOME/Library/Logs"
MAX_SIZE=$((5 * 1024 * 1024))  # 5 MB
KEEP=3

LOGS=(
    "email-nurse.log"
    "email-nurse-error.log"
    "email-nurse-mail-restart.log"
    "email-nurse-digest.log"
    "email-nurse-ops.log"
    "email-nurse-brew-sysm.log"
    "email-nurse-brew-all.log"
    "email-nurse-brew-cleanup.log"
)

rotate_log() {
    local logfile="$1"
    local path="${LOG_DIR}/${logfile}"

    [[ ! -f "$path" ]] && return

    local size=$(stat -f%z "$path" 2>/dev/null || echo 0)
    if [[ $size -lt $MAX_SIZE ]]; then
        return
    fi

    echo "$(date '+%Y-%m-%d %H:%M:%S') Rotating $logfile ($(( size / 1024 / 1024 ))MB)"

    # Shift existing backups
    local i=$KEEP
    while [[ $i -gt 1 ]]; do
        local prev=$((i - 1))
        [[ -f "${path}.${prev}" ]] && mv "${path}.${prev}" "${path}.${i}"
        i=$((i - 1))
    done

    # Current -> .1
    mv "$path" "${path}.1"

    # Create fresh empty log
    touch "$path"
}

for logfile in "${LOGS[@]}"; do
    rotate_log "$logfile"
done
