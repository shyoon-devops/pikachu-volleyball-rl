#!/usr/bin/env bash
# Smoke test for deployed environments.
# Usage: smoke-test.sh <dev|qa|prod> [--fe-host HOST]
#
# Exits 0 when all required endpoints respond correctly, non-zero otherwise.
# Designed to run immediately after deploy/promote to catch regressions before
# traffic is shifted to the new build.
set -uo pipefail

ENV="${1:-}"
FE_HOST="${FE_HOST:-${FRONTEND_HOST:-localhost}}"
shift || true
while [ $# -gt 0 ]; do
    case "$1" in
        --fe-host) FE_HOST="$2"; shift 2 ;;
        *) echo "unknown arg: $1"; exit 2 ;;
    esac
done

case "$ENV" in
    dev)  BE_PORT=8001; FE_PORT=3000 ;;
    qa)   BE_PORT=8002; FE_PORT=3001 ;;
    prod) BE_PORT=8003; FE_PORT=3002 ;;
    *) echo "Usage: $0 <dev|qa|prod> [--fe-host HOST]"; exit 2 ;;
esac

BE="http://localhost:${BE_PORT}"
FE="http://${FE_HOST}:${FE_PORT}"

PASS=0
FAIL=0
FAILED_CHECKS=()

run_check() {
    local name="$1"; shift
    local expected="$1"; shift
    local cmd="$*"
    local actual
    actual="$(eval "$cmd" 2>&1)" || true
    if echo "$actual" | grep -qE "$expected"; then
        printf "  [PASS] %-40s\n" "$name"
        PASS=$((PASS + 1))
    else
        printf "  [FAIL] %-40s (got: %s)\n" "$name" "$(echo "$actual" | head -c 80)"
        FAIL=$((FAIL + 1))
        FAILED_CHECKS+=("$name")
    fi
}

echo "=== Smoke test: $ENV ==="
echo "  Backend:  $BE"
echo "  Frontend: $FE"
echo ""

echo "--- Backend health ---"
run_check "GET /api/health"            '"status":"ok"'       "timeout 5 curl -sf $BE/api/health"
run_check "GET /api/training/status"   'state'               "timeout 5 curl -sf $BE/api/training/status"
run_check "GET /api/games"             '"data"|"total"|items' "timeout 5 curl -sf $BE/api/games"
run_check "GET /api/models"            '"models"|"data"|items' "timeout 5 curl -sf $BE/api/models"
run_check "GET /metrics (Prometheus)"  'pikachu_|http_'      "timeout 5 curl -sf $BE/metrics"
run_check "GET /docs (OpenAPI UI)"     'swagger|Swagger'     "timeout 5 curl -sf $BE/docs"

echo ""
echo "--- WebSocket reachability ---"
# 16 random bytes base64-encoded, required by RFC 6455
WS_KEY="$(head -c 16 /dev/urandom 2>/dev/null | base64 || echo 'AAAAAAAAAAAAAAAAAAAAAA==')"
# curl -v writes response headers to stderr; --max-time bounds the socket wait since the
# upgraded connection otherwise stays open after 101 Switching Protocols.
run_check "WS /ws handshake (101)" "101 Switching Protocols" \
    "curl -sv --http1.1 --max-time 2 -H 'Connection: Upgrade' -H 'Upgrade: websocket' -H 'Sec-WebSocket-Version: 13' -H 'Sec-WebSocket-Key: $WS_KEY' $BE/ws 2>&1 | head -40"

echo ""
echo "--- Frontend reachability ---"
run_check "GET / (index)"      '<!DOCTYPE html|<!doctype html' "timeout 8 curl -sf $FE/"
run_check "GET /assets (hash)" 'assets|pikachu|volleyball'     "timeout 8 curl -s $FE/ | grep -Eo '(assets/[^\"]+|pikachu|volleyball)' | head -1"

echo ""
echo "--- Security headers ---"
run_check "X-Content-Type-Options" "nosniff"   "timeout 5 curl -sI $FE/"
run_check "X-Frame-Options"        "DENY|SAMEORIGIN" "timeout 5 curl -sI $FE/"

echo ""
echo "--- Container health ---"
DOCKER_BIN="${DOCKER:-docker}"
if ! command -v "$DOCKER_BIN" >/dev/null 2>&1; then
    DOCKER_BIN="docker.exe"
fi
for svc in backend mongodb; do
    name="pikachu-rl-${ENV}-${svc}-1"
    run_check "container $name" "healthy|Up" \
        "timeout 5 $DOCKER_BIN ps --filter name=$name --format '{{.Status}}'"
done

echo ""
echo "=== Result: $PASS passed, $FAIL failed ==="
if [ "$FAIL" -gt 0 ]; then
    echo "Failed checks:"
    printf '  - %s\n' "${FAILED_CHECKS[@]}"
    exit 1
fi
exit 0
