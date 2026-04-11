#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
REPLAY_DIR="${PROJECT_DIR}/replays"
MAX_REPLAYS="${1:-1000}"

if [ ! -d "$REPLAY_DIR" ]; then
    echo "Replay directory not found: $REPLAY_DIR"
    exit 0
fi

TOTAL=$(find "$REPLAY_DIR" -name "*.msgpack" -type f | wc -l)

if [ "$TOTAL" -le "$MAX_REPLAYS" ]; then
    echo "Replay count ($TOTAL) within limit ($MAX_REPLAYS). Nothing to clean."
    exit 0
fi

DELETE_COUNT=$((TOTAL - MAX_REPLAYS))

echo "Total replays: $TOTAL, limit: $MAX_REPLAYS"
echo "Deleting $DELETE_COUNT oldest replays..."

find "$REPLAY_DIR" -name "*.msgpack" -type f -printf '%T+ %p\n' \
    | sort \
    | head -n "$DELETE_COUNT" \
    | awk '{print $2}' \
    | xargs rm -f

echo "Done. Remaining: $(find "$REPLAY_DIR" -name "*.msgpack" -type f | wc -l)"
