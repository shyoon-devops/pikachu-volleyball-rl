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
        # Also rebuild dev backend to guarantee dev == github/dev HEAD. Without
        # this, merges into dev (e.g. hotfixes) leave the dev backend running
        # a stale image until someone manually runs deploy-dev.sh — the exact
        # failure mode PM hit on 2026-04-12 (dev :8001 served a 15h-old image
        # missing BE-6 WS hotfix and anti-toss-loop fix). See DEPLOYMENT-STATUS.md.
        PRE_DEPLOY_SCRIPT="$SCRIPT_DIR/deploy-dev.sh"
        ;;
    qa-to-prod)
        SOURCE_BRANCH="qa"
        TARGET_BRANCH="main"
        DEPLOY_SCRIPT="$SCRIPT_DIR/deploy-prod.sh"
        PRE_DEPLOY_SCRIPT=""
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

# Rebuild source environment first (dev-to-qa only). Ensures the image running
# on :8001 matches the commit we are about to promote to qa. If dev was already
# in sync, this is a fast no-op rebuild; if dev was stale, this catches it
# before the staler image reaches a second environment.
if [ -n "$PRE_DEPLOY_SCRIPT" ]; then
    echo ""
    echo "Pre-deploy sync: $PRE_DEPLOY_SCRIPT"
    bash "$PRE_DEPLOY_SCRIPT"
fi

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
