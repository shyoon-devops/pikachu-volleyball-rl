#!/usr/bin/env bash
# Regenerate backend/tests/fixtures/original_frames.json from the
# upstream gorisanson/pikachu-volleyball physics.js using the harness
# at /tmp/parity-harness/run.mjs.
#
# Run this when:
#   - upstream physics.js changes
#   - the input script in run.mjs / test_parity_with_original.py changes
#   - the Mulberry32 seed changes
#
# Requires: Node.js, an existing /tmp/pikachu-original/ clone (see
# ATTRIBUTION.md for the upstream URL), and /tmp/parity-harness/
# wired up (run.mjs + package.json {"type": "module"} + a copy of
# physics.js + rand.js from the upstream).
#
# Usage from repo root:
#   bash backend/scripts/regenerate_parity_fixture.sh

set -euo pipefail
cd /tmp/parity-harness
node run.mjs > "$(git -C "$OLDPWD" rev-parse --show-toplevel)/backend/tests/fixtures/original_frames.json"
echo "regenerated: backend/tests/fixtures/original_frames.json"
