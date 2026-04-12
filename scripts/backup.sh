#!/usr/bin/env bash
# Backup MongoDB data + model checkpoints for a given environment.
#
# Usage:
#   ./scripts/backup.sh dev       # Backup dev environment
#   ./scripts/backup.sh qa        # Backup QA environment
#   ./scripts/backup.sh prod      # Backup prod environment
#
# Retention: 7 daily + 4 weekly backups.
# Schedule (add to crontab):
#   0 3 * * * /path/to/scripts/backup.sh dev   >> /var/log/pikachu-backup-dev.log 2>&1
#   0 4 * * * /path/to/scripts/backup.sh prod  >> /var/log/pikachu-backup-prod.log 2>&1

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
source "$SCRIPT_DIR/_common.sh"

ENV="${1:-}"
if [[ -z "$ENV" || ! "$ENV" =~ ^(dev|qa|prod)$ ]]; then
    echo "Usage: $0 <dev|qa|prod>"
    exit 1
fi

# --- Configuration ---
BACKUP_ROOT="${BACKUP_ROOT:-$PROJECT_DIR/backups}"
BACKUP_DIR="$BACKUP_ROOT/$ENV"
DATE="$(date +%Y%m%d_%H%M%S)"
DAY_OF_WEEK="$(date +%u)"  # 1=Monday, 7=Sunday

DAILY_RETAIN=7
WEEKLY_RETAIN=4

# Port mapping per environment
case "$ENV" in
    dev)  MONGO_PORT=27018 ;;
    qa)   MONGO_PORT=27019 ;;
    prod) MONGO_PORT=27020 ;;
esac

MONGO_CONTAINER="pikachu-rl-${ENV}-mongodb-1"
DB_NAME="pikachu_rl"

# --- Directories ---
DAILY_DIR="$BACKUP_DIR/daily"
WEEKLY_DIR="$BACKUP_DIR/weekly"
mkdir -p "$DAILY_DIR" "$WEEKLY_DIR"

echo "=== Pikachu RL Backup — $ENV ==="
echo "  Date:      $DATE"
echo "  Backup to: $BACKUP_DIR"
echo ""

# --- 1. MongoDB dump ---
MONGO_BACKUP="$DAILY_DIR/mongodb_${DATE}"
echo "[1/3] Dumping MongoDB ($MONGO_CONTAINER:$MONGO_PORT)..."

if $DOCKER ps --format '{{.Names}}' | grep -q "^${MONGO_CONTAINER}$"; then
    $DOCKER exec "$MONGO_CONTAINER" \
        mongodump --db="$DB_NAME" --archive --gzip \
        > "${MONGO_BACKUP}.archive.gz"
    MONGO_SIZE=$(du -h "${MONGO_BACKUP}.archive.gz" | cut -f1)
    echo "  MongoDB dump: ${MONGO_SIZE} -> ${MONGO_BACKUP}.archive.gz"
else
    echo "  WARNING: MongoDB container $MONGO_CONTAINER is not running. Skipping DB backup."
    MONGO_BACKUP=""
fi

# --- 2. Model checkpoints ---
MODELS_DIR="$PROJECT_DIR/models"
MODELS_BACKUP="$DAILY_DIR/models_${DATE}.tar.gz"

echo "[2/3] Backing up model checkpoints..."
if [[ -d "$MODELS_DIR" && "$(ls -A "$MODELS_DIR" 2>/dev/null)" ]]; then
    tar -czf "$MODELS_BACKUP" -C "$PROJECT_DIR" models/
    MODELS_SIZE=$(du -h "$MODELS_BACKUP" | cut -f1)
    echo "  Models archive: ${MODELS_SIZE} -> $MODELS_BACKUP"
else
    echo "  No model checkpoints found in $MODELS_DIR. Skipping."
    MODELS_BACKUP=""
fi

# --- 3. Weekly copy (Sundays) ---
echo "[3/3] Checking weekly backup schedule..."
if [[ "$DAY_OF_WEEK" == "7" ]]; then
    echo "  Sunday — creating weekly backup copy..."
    [[ -n "$MONGO_BACKUP" && -f "${MONGO_BACKUP}.archive.gz" ]] && \
        cp "${MONGO_BACKUP}.archive.gz" "$WEEKLY_DIR/mongodb_${DATE}.archive.gz"
    [[ -n "$MODELS_BACKUP" && -f "$MODELS_BACKUP" ]] && \
        cp "$MODELS_BACKUP" "$WEEKLY_DIR/models_${DATE}.tar.gz"
    echo "  Weekly backup created."
else
    echo "  Not Sunday — skipping weekly copy."
fi

# --- 4. Rotation — prune old backups ---
echo ""
echo "Rotating old backups..."

rotate_backups() {
    local dir="$1"
    local pattern="$2"
    local keep="$3"
    local label="$4"

    local count
    count=$(find "$dir" -maxdepth 1 -name "$pattern" -type f | wc -l)
    if [[ "$count" -gt "$keep" ]]; then
        local to_delete=$((count - keep))
        find "$dir" -maxdepth 1 -name "$pattern" -type f -printf '%T@ %p\n' \
            | sort -n | head -n "$to_delete" | cut -d' ' -f2- \
            | while read -r f; do
                echo "  Pruning $label: $(basename "$f")"
                rm -f "$f"
            done
    fi
}

rotate_backups "$DAILY_DIR" "mongodb_*.archive.gz" "$DAILY_RETAIN" "daily mongo"
rotate_backups "$DAILY_DIR" "models_*.tar.gz"      "$DAILY_RETAIN" "daily models"
rotate_backups "$WEEKLY_DIR" "mongodb_*.archive.gz" "$WEEKLY_RETAIN" "weekly mongo"
rotate_backups "$WEEKLY_DIR" "models_*.tar.gz"      "$WEEKLY_RETAIN" "weekly models"

# --- Summary ---
echo ""
echo "=== Backup complete ==="
TOTAL_SIZE=$(du -sh "$BACKUP_DIR" 2>/dev/null | cut -f1)
echo "  Total backup size ($ENV): ${TOTAL_SIZE:-0}"
echo "  Daily backups:  $(find "$DAILY_DIR" -maxdepth 1 -type f | wc -l) files"
echo "  Weekly backups: $(find "$WEEKLY_DIR" -maxdepth 1 -type f | wc -l) files"
