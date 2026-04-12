#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_DIR"

echo "=== Deploying DEV environment ==="
echo "  Backend:  http://localhost:8001"
echo "  Frontend: http://localhost:3000"
echo "  MongoDB:  localhost:27018"
echo ""

docker compose -f docker-compose.dev.yml up --build -d

echo ""
echo "=== DEV deployment complete ==="
