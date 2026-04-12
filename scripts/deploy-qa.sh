#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
source "$SCRIPT_DIR/_common.sh"

cd "$PROJECT_DIR"

echo "=== Deploying QA environment ==="
echo "  Backend:  http://localhost:8002"
echo "  Frontend: http://192.168.0.248:3001"
echo "  MongoDB:  localhost:27019"
echo ""

$DOCKER compose -f docker-compose.qa.yml up --build -d --remove-orphans

$DOCKER image prune -f >/dev/null 2>&1 || true

echo ""
echo "=== QA deployment complete ==="
