#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
source "$SCRIPT_DIR/_common.sh"

cd "$PROJECT_DIR"

echo "=== Pikachu Volleyball RL — Setup ==="

# Create required directories
mkdir -p models replays
echo "[OK] Created models/ and replays/ directories"

# Copy .env if not exists
if [ ! -f .env ]; then
    cp .env.example .env
    echo "[OK] Created .env from .env.example"
else
    echo "[SKIP] .env already exists"
fi

# Start the stack
echo ""
echo "Starting Docker Compose..."
$DOCKER compose up --build -d

echo ""
echo "=== Setup complete ==="
echo "  Frontend: http://localhost:5173"
echo "  Backend:  http://localhost:8000"
echo "  MongoDB:  localhost:27017"
