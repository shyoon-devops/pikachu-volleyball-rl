#!/usr/bin/env bash
# Shared helpers for deploy scripts.
# Source this file: source "$(dirname "$0")/_common.sh"

DOCKER="docker"

# Local deployment settings (hosts, SSH key, CORS origins). Values already set in
# the environment (e.g. GitHub Actions variables) take precedence.
_DEPLOY_ENV="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/deploy.env"
if [ -f "$_DEPLOY_ENV" ]; then
    while IFS='=' read -r _k _v; do
        [[ -z "$_k" || "$_k" == \#* ]] && continue
        [[ -n "${!_k:-}" ]] && continue
        eval "export $_k=\"$_v\""
    done < "$_DEPLOY_ENV"
fi
FRONTEND_HOST="${FRONTEND_HOST:-localhost}"
