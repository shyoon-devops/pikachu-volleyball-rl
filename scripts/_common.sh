#!/usr/bin/env bash
# Shared helpers for deploy scripts.
# Source this file: source "$(dirname "$0")/_common.sh"

if grep -qi microsoft /proc/version 2>/dev/null; then
    DOCKER="docker.exe"
else
    DOCKER="docker"
fi
