#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

ENV="${1:-dev}"
NO_PUSH=false
for arg in "$@"; do
    [[ "$arg" == "--no-push" ]] && NO_PUSH=true
done

SSH_KEY="$HOME/.ssh/id_ed25519_yoonbian-2"
SSH_HOST="yoon@192.168.0.248"
SSH_CMD="ssh -i $SSH_KEY $SSH_HOST"
REMOTE_DIR="/home/yoon/pikachu-frontend/${ENV}/dist"

# Validate environment
case "$ENV" in
    dev|qa|prod) ;;
    *) echo "Usage: $0 <dev|qa|prod> [--no-push]"; exit 1 ;;
esac

# Capture the SHA we're about to deploy (local HEAD drives `npm run build`)
cd "$PROJECT_DIR"
DEPLOY_SHA="$(git rev-parse HEAD)"
DEPLOY_SHORT="$(git rev-parse --short HEAD)"

echo "=== Deploying Frontend ($ENV) to yoonbian-2 ==="
echo "    Source SHA: $DEPLOY_SHORT ($DEPLOY_SHA)"
echo ""

# 1. Build frontend locally
echo "[1/6] Building frontend..."
cd "$PROJECT_DIR/frontend"
npm ci --silent
npm run build

# 2. Create remote directory
echo "[2/6] Preparing remote directory..."
$SSH_CMD "mkdir -p $REMOTE_DIR"

# 3. Sync build output
echo "[3/6] Syncing dist/ to yoonbian-2..."
rsync -avz --delete \
    dist/ \
    "$SSH_HOST:$REMOTE_DIR/" \
    -e "ssh -i $SSH_KEY"

# 4. Fix permissions for nginx (www-data) access
echo "[4/6] Setting permissions..."
$SSH_CMD "chmod o+x /home/yoon /home/yoon/pikachu-frontend && \
    chmod -R o+rX /home/yoon/pikachu-frontend/"

# 5. Deploy nginx config
echo "[5/6] Deploying nginx config..."
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

# 6. Auto-advance env ref so github/${ENV} reflects what was just deployed.
#    Prevents the stale-branch drift documented in
#    docs/incidents/20260412-dev-backend-stale.md § Recurrence.
#    Fast-forward only — non-ff is surfaced as a warning, never silently forced.
echo "[6/6] Advancing github/$ENV ref to $DEPLOY_SHORT..."
cd "$PROJECT_DIR"
if $NO_PUSH; then
    echo "  --no-push set; skipping ref advance."
else
    # Confirm env remote branch exists before attempting push
    if ! git ls-remote --exit-code --heads github "$ENV" >/dev/null 2>&1; then
        echo "  WARN: github/$ENV does not exist; skipping (nothing to advance)."
    else
        REMOTE_SHA="$(git ls-remote github "refs/heads/$ENV" | awk '{print $1}')"
        if [[ "$REMOTE_SHA" == "$DEPLOY_SHA" ]]; then
            echo "  github/$ENV already at $DEPLOY_SHORT — nothing to do."
        elif git merge-base --is-ancestor "$REMOTE_SHA" "$DEPLOY_SHA" 2>/dev/null; then
            if git push github "${DEPLOY_SHA}:${ENV}" 2>&1; then
                echo "  github/$ENV fast-forwarded: $(git rev-parse --short "$REMOTE_SHA") → $DEPLOY_SHORT"
            else
                echo ""
                echo "  WARN: push to github/$ENV failed despite FF ancestry."
                echo "  WARN: deploy itself succeeded; ref did not advance."
            fi
        else
            echo ""
            echo "  WARN: github/$ENV ($(git rev-parse --short "$REMOTE_SHA")) is NOT an"
            echo "        ancestor of $DEPLOY_SHORT. Refusing to force. Deploy itself"
            echo "        succeeded, but the branch ref is now drifted from runtime."
            echo "        Resolve manually via merge or explicit force-with-lease."
        fi
    fi
fi

echo ""
echo "=== Frontend ($ENV) deployed to yoonbian-2 ==="
echo "    Runtime SHA: $DEPLOY_SHORT"
