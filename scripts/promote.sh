#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_DIR"

usage() {
    echo "Usage: $0 <dev-to-qa|qa-to-prod>"
    echo ""
    echo "Examples:"
    echo "  $0 dev-to-qa      # Merge develop -> qa and redeploy QA"
    echo "  $0 qa-to-prod     # Merge qa -> main and redeploy PROD"
    exit 1
}

if [ $# -ne 1 ]; then
    usage
fi

# Ensure working tree is clean
if [ -n "$(git status --porcelain)" ]; then
    echo "ERROR: Working tree is not clean. Commit or stash changes first."
    exit 1
fi

PROMOTION="$1"

case "$PROMOTION" in
    dev-to-qa)
        SOURCE_BRANCH="develop"
        TARGET_BRANCH="qa"
        DEPLOY_SCRIPT="$SCRIPT_DIR/deploy-qa.sh"
        ;;
    qa-to-prod)
        SOURCE_BRANCH="qa"
        TARGET_BRANCH="main"
        DEPLOY_SCRIPT="$SCRIPT_DIR/deploy-prod.sh"
        ;;
    *)
        usage
        ;;
esac

echo "=== Promoting: $SOURCE_BRANCH -> $TARGET_BRANCH ==="
echo ""

CURRENT_BRANCH="$(git branch --show-current)"

# Fetch latest
git fetch origin

# Checkout target and merge
git checkout "$TARGET_BRANCH"
git pull origin "$TARGET_BRANCH"
git merge "origin/$SOURCE_BRANCH" --no-edit -m "chore: promote $SOURCE_BRANCH to $TARGET_BRANCH"

echo ""
echo "Merge complete. Pushing to origin..."
git push origin "$TARGET_BRANCH"

echo ""
echo "Running deployment..."
bash "$DEPLOY_SCRIPT"

# Return to original branch
git checkout "$CURRENT_BRANCH"

echo ""
echo "=== Promotion $PROMOTION complete ==="
