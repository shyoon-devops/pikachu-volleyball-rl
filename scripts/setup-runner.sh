#!/usr/bin/env bash
set -euo pipefail

RUNNER_VERSION="2.321.0"
RUNNER_DIR="${HOME}/actions-runner"
REPO_URL="https://github.com/shyoon-devops/pikachu-volleyball-rl"

usage() {
    echo "Usage: $0 <GITHUB_RUNNER_TOKEN>"
    echo ""
    echo "Get the token from:"
    echo "  ${REPO_URL}/settings/actions/runners/new"
    echo ""
    echo "This script installs GitHub Actions self-hosted runner v${RUNNER_VERSION}."
    echo "Requires: curl, tar, sudo"
    exit 1
}

if [ $# -lt 1 ]; then
    usage
fi

TOKEN="$1"

echo "=== Installing GitHub Actions Self-Hosted Runner ==="
echo "  Version:  v${RUNNER_VERSION}"
echo "  Dir:      ${RUNNER_DIR}"
echo "  Repo:     ${REPO_URL}"
echo ""

# Create directory
mkdir -p "$RUNNER_DIR"
cd "$RUNNER_DIR"

# Download
ARCHIVE="actions-runner-linux-x64-${RUNNER_VERSION}.tar.gz"
if [ ! -f "$ARCHIVE" ]; then
    echo "Downloading runner v${RUNNER_VERSION}..."
    curl -o "$ARCHIVE" -L \
        "https://github.com/actions/runner/releases/download/v${RUNNER_VERSION}/${ARCHIVE}"
else
    echo "Archive already downloaded, skipping."
fi

# Extract
echo "Extracting..."
tar xzf "$ARCHIVE"

# Configure
echo ""
echo "Configuring runner..."
./config.sh --url "$REPO_URL" --token "$TOKEN" --unattended --replace

# Install and start as service
echo ""
echo "Installing as systemd service..."
sudo ./svc.sh install
sudo ./svc.sh start

echo ""
echo "=== Self-hosted runner installed and running ==="
echo ""
echo "Verify at: ${REPO_URL}/settings/actions/runners"
echo ""
echo "Commands:"
echo "  sudo ./svc.sh status   # Check status"
echo "  sudo ./svc.sh stop     # Stop runner"
echo "  sudo ./svc.sh start    # Start runner"
