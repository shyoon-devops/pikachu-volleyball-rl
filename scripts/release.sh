#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_DIR"

usage() {
    echo "Usage: $0 <major|minor|patch> [description]"
    echo ""
    echo "Examples:"
    echo "  $0 patch \"Fix training metrics export\""
    echo "  $0 minor \"Add model comparison dashboard\""
    echo "  $0 major \"Rewrite RL training pipeline\""
    exit 1
}

if [ $# -lt 1 ]; then
    usage
fi

BUMP_TYPE="$1"
DESCRIPTION="${2:-}"

# Read current version
if [ ! -f VERSION ]; then
    echo "0.1.0" > VERSION
fi

CURRENT_VERSION="$(cat VERSION | tr -d '[:space:]')"
IFS='.' read -r MAJOR MINOR PATCH <<< "$CURRENT_VERSION"

# Bump
case "$BUMP_TYPE" in
    major)
        MAJOR=$((MAJOR + 1))
        MINOR=0
        PATCH=0
        ;;
    minor)
        MINOR=$((MINOR + 1))
        PATCH=0
        ;;
    patch)
        PATCH=$((PATCH + 1))
        ;;
    *)
        usage
        ;;
esac

NEW_VERSION="${MAJOR}.${MINOR}.${PATCH}"
TODAY="$(date +%Y-%m-%d)"

echo "Bumping version: $CURRENT_VERSION -> $NEW_VERSION"

# Update VERSION file
echo "$NEW_VERSION" > VERSION

# Update CHANGELOG.md
if [ -n "$DESCRIPTION" ]; then
    CHANGELOG_ENTRY="## [$NEW_VERSION] - $TODAY\n\n### Changed\n- $DESCRIPTION"
else
    CHANGELOG_ENTRY="## [$NEW_VERSION] - $TODAY\n\n### Changed\n- Release $NEW_VERSION"
fi

# Insert new entry after the header block (after the first ## line pattern)
if grep -q "^## \[" CHANGELOG.md; then
    sed -i "0,/^## \[/s/^## \[/${CHANGELOG_ENTRY}\n\n## [/" CHANGELOG.md
else
    echo -e "\n${CHANGELOG_ENTRY}" >> CHANGELOG.md
fi

echo "Updated VERSION to $NEW_VERSION"
echo "Updated CHANGELOG.md"

# Commit and tag
git add VERSION CHANGELOG.md
git commit -m "chore: release v${NEW_VERSION}"
git tag -a "v${NEW_VERSION}" -m "Release v${NEW_VERSION}"

echo ""
echo "=== Release v${NEW_VERSION} created ==="
echo "Run 'git push origin main --tags' to publish."
