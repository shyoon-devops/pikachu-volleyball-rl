#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
source "$SCRIPT_DIR/_common.sh"

cd "$PROJECT_DIR"

echo "=== Deploying DEV environment ==="
echo "  Backend:  http://localhost:8001"
echo "  Frontend: http://${FRONTEND_HOST}:3000"
echo "  MongoDB:  localhost:27018"
echo ""

# --remove-orphans: kill containers for services removed from the compose file
# (e.g. the pre-two-server `frontend` service). Without this, orphans linger
# across refactors, consuming ports and disk.
$DOCKER compose -f docker-compose.dev.yml up --build -d --remove-orphans

# Reclaim disk from images untagged by the rebuild. Dangling-only — never -a.
$DOCKER image prune -f >/dev/null 2>&1 || true

echo ""
echo "=== DEV deployment complete ==="
