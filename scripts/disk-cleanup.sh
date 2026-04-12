#!/usr/bin/env bash
# Disk cleanup — Docker prune, model/replay rotation, tmp cleanup, disk alert.
#
# Usage:
#   ./scripts/disk-cleanup.sh              # Run all cleanup tasks
#   ./scripts/disk-cleanup.sh --dry-run    # Show what would be deleted
#
# Schedule (crontab):
#   0 5 * * * /path/to/scripts/disk-cleanup.sh >> /var/log/pikachu-disk-cleanup.log 2>&1

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
source "$SCRIPT_DIR/_common.sh"

DRY_RUN=false
[[ "${1:-}" == "--dry-run" ]] && DRY_RUN=true

# --- Configuration ---
MAX_MODEL_CHECKPOINTS=5     # per experiment directory
MAX_REPLAYS=1000            # NFR2.4
DISK_WARN_PERCENT=80
TMP_MAX_AGE_DAYS=7

TOTAL_FREED=0
DATE="$(date '+%Y-%m-%d %H:%M:%S')"

echo "=== Disk Cleanup — $DATE ==="
$DRY_RUN && echo "  ** DRY RUN — no files will be deleted **"
echo ""

# -------------------------------------------------------
# 1. Docker system prune
# -------------------------------------------------------
echo "[1/5] Docker cleanup (dangling images, stopped containers, unused networks)..."

if $DRY_RUN; then
    echo "  [dry-run] would run: docker system prune -f --filter until=72h"
    echo "  [dry-run] would run: docker builder prune -f --filter until=168h"
    echo "  Dangling images: $($DOCKER images -f dangling=true -q 2>/dev/null | wc -l)"
    echo "  Stopped containers: $($DOCKER ps -a -f status=exited -q 2>/dev/null | wc -l)"
else
    $DOCKER system prune -f --filter "until=72h" 2>/dev/null || true
    $DOCKER builder prune -f --filter "until=168h" 2>/dev/null || true
    echo "  Docker prune complete"
fi
echo ""

# -------------------------------------------------------
# 2. Model checkpoint rotation (keep latest N per experiment)
# -------------------------------------------------------
MODELS_DIR="$PROJECT_DIR/models"
echo "[2/5] Model checkpoint cleanup (keep latest $MAX_MODEL_CHECKPOINTS per experiment)..."

if [[ -d "$MODELS_DIR" ]]; then
    MODELS_DELETED=0
    for exp_dir in "$MODELS_DIR"/*/; do
        [[ -d "$exp_dir" ]] || continue
        exp_name="$(basename "$exp_dir")"

        # Count .zip checkpoint files
        zip_count=$(find "$exp_dir" -maxdepth 1 -name "*.zip" -type f | wc -l)
        if [[ "$zip_count" -le "$MAX_MODEL_CHECKPOINTS" ]]; then
            continue
        fi

        to_delete=$((zip_count - MAX_MODEL_CHECKPOINTS))
        echo "  $exp_name: $zip_count checkpoints, pruning $to_delete"

        find "$exp_dir" -maxdepth 1 -name "*.zip" -type f -printf '%T@ %p\n' \
            | sort -n | head -n "$to_delete" | cut -d' ' -f2- \
            | while read -r f; do
                if $DRY_RUN; then
                    echo "    [dry-run] would delete: $(basename "$f")"
                else
                    rm -f "$f"
                    MODELS_DELETED=$((MODELS_DELETED + 1))
                fi
            done
    done
    echo "  Deleted $MODELS_DELETED checkpoint files"
else
    echo "  No models/ directory found. Skipping."
fi
echo ""

# -------------------------------------------------------
# 3. Replay data rotation (keep latest MAX_REPLAYS)
# -------------------------------------------------------
REPLAY_DIR="$PROJECT_DIR/replays"
echo "[3/5] Replay cleanup (keep latest $MAX_REPLAYS, NFR2.4)..."

if [[ -d "$REPLAY_DIR" ]]; then
    replay_count=$(find "$REPLAY_DIR" -name "*.msgpack" -type f | wc -l)
    if [[ "$replay_count" -gt "$MAX_REPLAYS" ]]; then
        to_delete=$((replay_count - MAX_REPLAYS))
        echo "  $replay_count replays found, pruning $to_delete"

        if $DRY_RUN; then
            echo "  [dry-run] would delete $to_delete oldest replays"
        else
            find "$REPLAY_DIR" -name "*.msgpack" -type f -printf '%T@ %p\n' \
                | sort -n | head -n "$to_delete" | cut -d' ' -f2- \
                | xargs rm -f
            echo "  Deleted $to_delete replay files"
        fi
    else
        echo "  $replay_count replays — within limit. Skipping."
    fi
else
    echo "  No replays/ directory found. Skipping."
fi
echo ""

# -------------------------------------------------------
# 4. /tmp cleanup (files older than N days)
# -------------------------------------------------------
echo "[4/5] Temp file cleanup (/tmp files older than ${TMP_MAX_AGE_DAYS}d)..."

tmp_count="$(find /tmp -maxdepth 2 -user "$(whoami)" -type f -mtime +"$TMP_MAX_AGE_DAYS" 2>/dev/null | wc -l)" || tmp_count=0
if [[ "$tmp_count" -gt 0 ]]; then
    if $DRY_RUN; then
        echo "  [dry-run] would delete $tmp_count temp files"
    else
        find /tmp -maxdepth 2 -user "$(whoami)" -type f -mtime +"$TMP_MAX_AGE_DAYS" -delete 2>/dev/null || true
        echo "  Deleted $tmp_count temp files"
    fi
else
    echo "  No stale temp files. Skipping."
fi
echo ""

# -------------------------------------------------------
# 5. Disk usage monitor
# -------------------------------------------------------
echo "[5/5] Disk usage check (warn threshold: ${DISK_WARN_PERCENT}%)..."
echo ""

ALERT=false
# Filter to real block devices only (/dev/*), skip WSL mounts and virtual filesystems
while IFS= read -r line; do
    source=$(echo "$line" | awk '{print $1}')
    # Only check /dev/* block devices
    [[ "$source" == /dev/* ]] || continue
    # Skip Docker Desktop internal mounts
    [[ "$source" == /dev/loop* ]] && continue

    usage_pct=$(echo "$line" | awk '{print $5}' | tr -d '%')
    mount=$(echo "$line" | awk '{print $6}')
    size=$(echo "$line" | awk '{print $2}')
    used=$(echo "$line" | awk '{print $3}')
    avail=$(echo "$line" | awk '{print $4}')

    if [[ "$usage_pct" -ge "$DISK_WARN_PERCENT" ]]; then
        echo "  WARNING: $mount at ${usage_pct}% (used: $used / $size, avail: $avail)"
        ALERT=true
    else
        echo "  OK: $mount at ${usage_pct}% (avail: $avail)"
    fi
done < <(df -h --output=source,size,used,avail,pcent,target -x tmpfs -x devtmpfs -x overlay 2>/dev/null | tail -n +2)

echo ""
if $ALERT; then
    echo "=== ALERT: Disk usage above ${DISK_WARN_PERCENT}% on one or more mounts ==="
else
    echo "=== Disk cleanup complete — all mounts below ${DISK_WARN_PERCENT}% ==="
fi
