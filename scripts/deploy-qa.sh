#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_DIR"

echo "=== Deploying QA environment ==="
echo "  Backend:  http://localhost:8002"
echo "  Frontend: http://localhost:3001"
echo "  MongoDB:  localhost:27019"
echo ""

docker compose -f docker-compose.qa.yml up --build -d

echo ""
echo "=== QA deployment complete ==="
