#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

ENV="${1:-dev}"
SSH_KEY="$HOME/.ssh/id_ed25519_yoonbian-2"
SSH_HOST="yoon@192.168.0.248"
SSH_CMD="ssh -i $SSH_KEY $SSH_HOST"
REMOTE_DIR="/home/yoon/pikachu-frontend/${ENV}/dist"

# Validate environment
case "$ENV" in
    dev|qa|prod) ;;
    *) echo "Usage: $0 <dev|qa|prod>"; exit 1 ;;
esac

echo "=== Deploying Frontend ($ENV) to yoonbian-2 ==="
echo ""

# 1. Build frontend locally
echo "[1/4] Building frontend..."
cd "$PROJECT_DIR/frontend"
npm ci --silent
npm run build

# 2. Create remote directory
echo "[2/4] Preparing remote directory..."
$SSH_CMD "mkdir -p $REMOTE_DIR"

# 3. Sync build output
echo "[3/4] Syncing dist/ to yoonbian-2..."
rsync -avz --delete \
    dist/ \
    "$SSH_HOST:$REMOTE_DIR/" \
    -e "ssh -i $SSH_KEY"

# 4. Fix permissions for nginx (www-data) access
echo "[4/5] Setting permissions..."
$SSH_CMD "chmod o+x /home/yoon /home/yoon/pikachu-frontend && \
    chmod -R o+rX /home/yoon/pikachu-frontend/"

# 5. Deploy nginx config
echo "[5/5] Deploying nginx config..."
NGINX_CONF="$PROJECT_DIR/frontend/nginx-${ENV}.conf"
if [ ! -f "$NGINX_CONF" ]; then
    echo "ERROR: $NGINX_CONF not found"
    exit 1
fi

scp -i "$SSH_KEY" "$NGINX_CONF" "$SSH_HOST:/tmp/pikachu-${ENV}.conf"
$SSH_CMD "sudo cp /tmp/pikachu-${ENV}.conf /etc/nginx/sites-available/pikachu-${ENV} && \
    sudo ln -sf /etc/nginx/sites-available/pikachu-${ENV} /etc/nginx/sites-enabled/ && \
    sudo nginx -t && \
    sudo systemctl reload nginx"

echo ""
echo "=== Frontend ($ENV) deployed to yoonbian-2 ==="
