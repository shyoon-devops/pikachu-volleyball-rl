#!/usr/bin/env bash
# Restore MongoDB data from a backup archive.
#
# Usage:
#   ./scripts/restore.sh dev backups/dev/daily/mongodb_20260412_030000.archive.gz
#
# WARNING: This replaces the current database contents.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
source "$SCRIPT_DIR/_common.sh"

ENV="${1:-}"
ARCHIVE="${2:-}"

if [[ -z "$ENV" || ! "$ENV" =~ ^(dev|qa|prod)$ ]] || [[ -z "$ARCHIVE" ]]; then
    echo "Usage: $0 <dev|qa|prod> <path/to/mongodb_*.archive.gz>"
    exit 1
fi

if [[ ! -f "$ARCHIVE" ]]; then
    echo "ERROR: Archive not found: $ARCHIVE"
    exit 1
fi

MONGO_CONTAINER="pikachu-rl-${ENV}-mongodb-1"
DB_NAME="pikachu_rl"

echo "=== Pikachu RL Restore — $ENV ==="
echo "  Archive: $ARCHIVE"
echo "  Target:  $MONGO_CONTAINER / $DB_NAME"
echo ""
echo "WARNING: This will DROP the existing '$DB_NAME' database and replace it."
read -rp "Continue? [y/N] " confirm
if [[ "$confirm" != "y" && "$confirm" != "Y" ]]; then
    echo "Aborted."
    exit 0
fi

echo ""
echo "Restoring..."
cat "$ARCHIVE" | $DOCKER exec -i "$MONGO_CONTAINER" \
    mongorestore --archive --gzip --drop --db="$DB_NAME"

echo ""
echo "=== Restore complete ==="
