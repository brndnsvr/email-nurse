#!/bin/bash
# Backup autopilot.yaml with date stamp, keeping last 33 backups

set -euo pipefail

SOURCE="$HOME/.config/email-nurse/autopilot.yaml"
BACKUP_DIR="/Users/bss/code/email-nurse/backups"
DATE=$(date +%Y%m%d)
DEST="$BACKUP_DIR/autopilot_${DATE}.yaml"
MAX_BACKUPS=33

# Ensure backup directory exists
mkdir -p "$BACKUP_DIR"

# Only backup if source exists
if [[ ! -f "$SOURCE" ]]; then
    echo "Source file not found: $SOURCE" >&2
    exit 1
fi

# Copy with date stamp (overwrites if same day)
cp "$SOURCE" "$DEST"
echo "Backed up to $DEST"

# Remove old backups beyond MAX_BACKUPS
cd "$BACKUP_DIR"
BACKUP_COUNT=$(ls -1 autopilot_*.yaml 2>/dev/null | wc -l | tr -d ' ')

if [[ "$BACKUP_COUNT" -gt "$MAX_BACKUPS" ]]; then
    TO_DELETE=$((BACKUP_COUNT - MAX_BACKUPS))
    ls -1t autopilot_*.yaml | tail -n "$TO_DELETE" | while read -r old_file; do
        echo "Removing old backup: $old_file"
        rm "$old_file"
    done
fi

echo "Backup complete. $BACKUP_COUNT backups retained."
