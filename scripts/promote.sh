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

REMOTE="${GIT_REMOTE:-github}"

case "$PROMOTION" in
    dev-to-qa)
        SOURCE_BRANCH="dev"
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

echo "=== Promoting: $SOURCE_BRANCH -> $TARGET_BRANCH (remote: $REMOTE) ==="
echo ""

CURRENT_BRANCH="$(git branch --show-current)"

# Verify target branch not checked out in another worktree
if git worktree list --porcelain | grep -q "^branch refs/heads/$TARGET_BRANCH$"; then
    WT_PATH="$(git worktree list | awk -v br="[$TARGET_BRANCH]" '$NF==br {print $1}')"
    if [ "$WT_PATH" != "$PROJECT_DIR" ]; then
        echo "ERROR: '$TARGET_BRANCH' is checked out in another worktree: $WT_PATH"
        echo "Free it up or run promote.sh from there."
        exit 1
    fi
fi

# Fetch latest from remote
git fetch "$REMOTE" "$SOURCE_BRANCH" "$TARGET_BRANCH"

# Checkout target and merge
git checkout "$TARGET_BRANCH"
git pull --ff-only "$REMOTE" "$TARGET_BRANCH"
git merge "$REMOTE/$SOURCE_BRANCH" --no-ff -m "chore: promote $SOURCE_BRANCH to $TARGET_BRANCH"

echo ""
echo "Merge complete. Pushing to $REMOTE..."
git push "$REMOTE" "$TARGET_BRANCH"

echo ""
echo "Running deployment: $DEPLOY_SCRIPT"
bash "$DEPLOY_SCRIPT"

# Return to original branch
git checkout "$CURRENT_BRANCH"

echo ""
echo "=== Promotion $PROMOTION complete ==="
