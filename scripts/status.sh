#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
source "$SCRIPT_DIR/_common.sh"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

ENVS=("dev" "qa" "prod")

COMPOSE_FILES=(
    "docker-compose.dev.yml"
    "docker-compose.qa.yml"
    "docker-compose.prod.yml"
)

BACKEND_PORTS=("8001" "8002" "8000")
FRONTEND_PORTS=("3000" "3001" "5173")
MONGO_PORTS=("27018" "27019" "27017")

check_health() {
    local url="$1"
    if curl -sf --max-time 3 "$url" > /dev/null 2>&1; then
        echo -e "${GREEN}UP${NC}"
    else
        echo -e "${RED}DOWN${NC}"
    fi
}

check_container() {
    local project="$1"
    local service="$2"
    local status
    status="$($DOCKER compose -p "$project" ps --format '{{.Status}}' "$service" 2>/dev/null || echo "")"
    if [ -z "$status" ]; then
        echo -e "${RED}NOT RUNNING${NC}"
    elif echo "$status" | grep -qi "up"; then
        echo -e "${GREEN}${status}${NC}"
    else
        echo -e "${YELLOW}${status}${NC}"
    fi
}

echo "============================================="
echo "  Pikachu Volleyball RL — Environment Status"
echo "============================================="
echo ""

if [ -f VERSION ]; then
    echo "Version: $(cat VERSION | tr -d '[:space:]')"
    echo ""
fi

for i in "${!ENVS[@]}"; do
    ENV="${ENVS[$i]}"
    PROJECT="pikachu-rl-${ENV}"
    BACKEND_PORT="${BACKEND_PORTS[$i]}"
    FRONTEND_PORT="${FRONTEND_PORTS[$i]}"
    MONGO_PORT="${MONGO_PORTS[$i]}"

    ENV_UPPER="$(echo "$ENV" | tr '[:lower:]' '[:upper:]')"
    echo "--- ${ENV_UPPER} ---"
    echo "  MongoDB  (:${MONGO_PORT})  : $(check_container "$PROJECT" mongodb)"
    echo "  Backend  (:${BACKEND_PORT})  : $(check_container "$PROJECT" backend)"
    echo "  Frontend (:${FRONTEND_PORT})  : $(check_health "http://192.168.0.248:${FRONTEND_PORT}")"
    echo "  API      : $(check_health "http://localhost:${BACKEND_PORT}/api/health")"
    echo ""
done

echo "============================================="
