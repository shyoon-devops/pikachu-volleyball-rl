#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
source "$SCRIPT_DIR/_common.sh"

cd "$PROJECT_DIR"

echo "=== Deploying PROD environment ==="
echo "  Backend:  http://localhost:8000"
echo "  Frontend: http://192.168.0.248:5173"
echo "  MongoDB:  localhost:27017"
echo ""

# Skip confirmation in CI environments
if [ -z "${CI:-}" ]; then
    read -rp "Are you sure you want to deploy to PROD? (y/N): " confirm
    if [[ "$confirm" != "y" && "$confirm" != "Y" ]]; then
        echo "Aborted."
        exit 0
    fi
fi

$DOCKER compose -f docker-compose.prod.yml up --build -d

echo ""
echo "=== PROD deployment complete ==="
