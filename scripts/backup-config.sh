#!/bin/bash
set -euo pipefail

# Backup production configs to repo backup/ folder
# Configs are gitignored - this is for local disaster recovery only

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"
BACKUP_DIR="$REPO_ROOT/backup"
PROD_CONFIG_DIR="$HOME/.config/email-nurse"

TIMESTAMP=$(date +%Y%m%d-%H%M%S)

mkdir -p "$BACKUP_DIR"

echo "Backing up production configs..."
echo "  From: $PROD_CONFIG_DIR"
echo "  To:   $BACKUP_DIR"

# Files to backup
CONFIG_FILES=(
    "autopilot.yaml"
    "rules.yaml"
    "templates.yaml"
    ".env"
)

backed_up=0
for file in "${CONFIG_FILES[@]}"; do
    src="$PROD_CONFIG_DIR/$file"
    if [[ -f "$src" ]]; then
        cp "$src" "$BACKUP_DIR/${file%.yaml}-${TIMESTAMP}.yaml" 2>/dev/null || \
        cp "$src" "$BACKUP_DIR/${file}-${TIMESTAMP}"
        echo "  ✓ $file"
        ((backed_up++))
    fi
done

# Also backup the database
if [[ -f "$PROD_CONFIG_DIR/autopilot.db" ]]; then
    cp "$PROD_CONFIG_DIR/autopilot.db" "$BACKUP_DIR/autopilot-${TIMESTAMP}.db"
    echo "  ✓ autopilot.db"
    ((backed_up++))
fi

# Keep only last 5 backups of each type
echo ""
echo "Cleaning old backups (keeping last 5)..."
for pattern in autopilot rules templates .env; do
    files=$(ls -t "$BACKUP_DIR"/${pattern}* 2>/dev/null | tail -n +6 || true)
    if [[ -n "$files" ]]; then
        echo "$files" | xargs rm -f
    fi
done

echo ""
echo "Backup complete: $backed_up files backed up"
