#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
source "$SCRIPT_DIR/_common.sh"

cd "$PROJECT_DIR"

echo "=== Deploying DEV environment ==="
echo "  Backend:  http://localhost:8001"
echo "  Frontend: http://192.168.0.248:3000"
echo "  MongoDB:  localhost:27018"
echo ""

$DOCKER compose -f docker-compose.dev.yml up --build -d

echo ""
echo "=== DEV deployment complete ==="
