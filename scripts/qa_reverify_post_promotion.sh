#!/usr/bin/env bash
# QA re-verification after dev→QA promotion (2026-04-12).
#
# Before rebuild — baseline captured:
#   QA backend image SHA: sha256:dab203bf580e72cc5...
#   QA frontend bundle:   assets/index-we-0u1Nl.js (839199 bytes)
#   QA frontend ETag:     "69db3c8d-cce1f"
#   Start button state:   DUPLICATE (TrainingControls "Start" + HyperparamForm "Start Training")
#   /api/metrics burst:   100-req → 20x200 / 80x429 (NOT yet exempt on QA)
#   /api/metrics on dev:  100-req → 100x200 / 0x429 (already exempt)
#
# Key promotion commits (via `git log github/qa..github/dev --oneline`):
#   * 38e29bdd fix(middleware): exempt metrics + health probes from rate limiter
#   * 9f050c87 fix(ui): remove duplicate Start button, unify training controls
#   * b0d0aaee fix: port game engine faithfully to gorisanson/pikachu-volleyball
#   * e5d765a0 fix: gate ball-player collision with isCollisionWithBallHappened
#   * fb1f5e64 perf(ws): parallel broadcast with serialize-once fan-out (BE-6)
#   * ee7a6c0b perf(db): declare hot-path MongoDB indexes at startup (BE-5)
#   * 407876ca feat: time-series endpoint for evaluation metrics
#   * f10b6c25 feat(replay): keyboard scrubbing
#   * 76005f52 feat: evaluation history persistence + CRUD
#   * 3cdef948 feat(design): D6-D10 training progress / tooltip / fullscreen
#   * 265e3c30 feat(ui): global ConnectionIndicator pill
#   * 0f32235e feat(rl): rebalance reward weights
#
# PM promotion checklist:
#   1. New frontend bundle hash at the QA frontend URL
#   2. All 4 backend suites pass (expected 48 pass / 0 fail / 3 skip)
#   3. Deterministic fails resolved (/api/models probes in test_burst_triggers_429)
#   4. Rate-limit exemption verified on /api/health AND /api/metrics
#   5. Duplicate Start button removed (count of `children:\`Start\`` goes 1 → 0)
#
# Usage:
#   bash scripts/qa_reverify_post_promotion.sh 2>&1 | tee /tmp/qa_reverify_$(date +%s).log

set -u  # Don't set -e — we want to collect all results, not abort on first fail

REPO="${REPO:-$(git -C "$(dirname "$0")" rev-parse --show-toplevel)}"
BACKEND=$REPO/backend
QA_BACKEND_URL=http://localhost:8002
QA_FRONTEND_URL="${QA_FRONTEND_URL:-http://${FRONTEND_HOST:-localhost}:3001}"

log() { printf "\n\033[1;34m=== %s ===\033[0m\n" "$*"; }
pass() { printf "\033[32m✅ %s\033[0m\n" "$*"; }
fail() { printf "\033[31m❌ %s\033[0m\n" "$*"; }
warn() { printf "\033[33m⚠️  %s\033[0m\n" "$*"; }

# ---------------------------------------------------------------------------
# 1. QA image SHA change check
# ---------------------------------------------------------------------------
log "Step 1 — QA backend image SHA"
new_sha=$(docker inspect pikachu-rl-qa-backend-1 --format '{{.Image}}' 2>/dev/null)
old_sha="sha256:dab203bf580e72cc5da1550f2cf8a5348b53fc1ea363aa651e386795ee442352"
echo "Before: $old_sha"
echo "Now:    $new_sha"
if [ "$new_sha" = "$old_sha" ]; then
  fail "QA image SHA unchanged — rebuild not yet complete. Aborting."
  exit 1
else
  pass "QA image rebuilt"
fi

# ---------------------------------------------------------------------------
# 2. Frontend bundle hash change
# ---------------------------------------------------------------------------
log "Step 2 — QA frontend bundle"
new_bundle=$(curl -sL --max-time 5 "$QA_FRONTEND_URL/" | grep -oE 'assets/index-[a-zA-Z0-9_-]+\.js' | head -1)
old_bundle="assets/index-we-0u1Nl.js"
echo "Before: $old_bundle"
echo "Now:    $new_bundle"
if [ "$new_bundle" = "$old_bundle" ]; then
  warn "Frontend bundle hash unchanged — frontend may not have been rebuilt"
else
  pass "Frontend bundle replaced: $new_bundle"
fi

# ---------------------------------------------------------------------------
# 3. Duplicate Start button removed
# ---------------------------------------------------------------------------
log "Step 3 — Duplicate Start button check"
if [ -n "$new_bundle" ]; then
  curl -s --max-time 10 "$QA_FRONTEND_URL/$new_bundle" > /tmp/qa_bundle_new.js
  start_count=$(grep -oF 'children:`Start`' /tmp/qa_bundle_new.js | wc -l)
  start_training_count=$(grep -oF 'children:`Start Training`' /tmp/qa_bundle_new.js | wc -l)
  echo "children:\`Start\` occurrences:          $start_count (expected: 0)"
  echo "children:\`Start Training\` occurrences: $start_training_count (expected: 1)"
  if [ "$start_count" -eq 0 ] && [ "$start_training_count" -ge 1 ]; then
    pass "Duplicate Start button removed — only 'Start Training' remains"
  elif [ "$start_count" -eq 0 ] && [ "$start_training_count" -eq 0 ]; then
    warn "No Start button found at all — may be minified differently; inspect manually"
  else
    fail "Duplicate Start button still present (count=$start_count)"
  fi
fi

# ---------------------------------------------------------------------------
# 4. Rate-limit exemption on /api/health + /api/metrics
# ---------------------------------------------------------------------------
# Commit 38e29bdd ("fix(middleware): exempt metrics + health probes from rate
# limiter") covers BOTH /api/health and /api/metrics. Pre-promotion baseline
# on QA: /api/metrics returns 80x 429 under 100-request burst. Post-promotion
# expectation: 0x 429.
log "Step 4 — rate-limit exemption (200-burst /api/health, 100-burst /api/metrics)"
python3 - <<EOF
import asyncio, httpx

async def burst(base, path, n):
    async with httpx.AsyncClient(base_url=base, timeout=15) as c:
        results = await asyncio.gather(
            *[c.get(path) for _ in range(n)],
            return_exceptions=True,
        )
    codes = [r.status_code for r in results if not isinstance(r, Exception)]
    return codes

async def main():
    base = "$QA_BACKEND_URL"
    failed = False

    # /api/health: 200-burst, expect 0x 429 / 0x 5xx
    codes = await burst(base, "/api/health", 200)
    c200 = codes.count(200); c429 = codes.count(429)
    c5xx = sum(1 for x in codes if x >= 500)
    ok = (c429 == 0 and c5xx == 0 and c200 >= 190)
    status = "\033[32m✅\033[0m" if ok else "\033[31m❌\033[0m"
    print(f"{status} /api/health (200-burst):  200x{c200}  429x{c429}  5xxx{c5xx}")
    if not ok: failed = True

    # /api/metrics: 100-burst, expect 0x 429 after promotion
    codes = await burst(base, "/api/metrics", 100)
    c200 = codes.count(200); c429 = codes.count(429)
    c5xx = sum(1 for x in codes if x >= 500)
    c404 = codes.count(404)
    ok = (c429 == 0 and c5xx == 0 and c404 == 0 and c200 >= 95)
    status = "\033[32m✅\033[0m" if ok else "\033[31m❌\033[0m"
    print(f"{status} /api/metrics (100-burst): 200x{c200}  429x{c429}  5xxx{c5xx}  404x{c404}")
    if not ok: failed = True

    raise SystemExit(1 if failed else 0)

asyncio.run(main())
EOF

# ---------------------------------------------------------------------------
# 5. Full backend suite
# ---------------------------------------------------------------------------
log "Step 5 — Full backend suite (test_sprint1 + test_rate_limiting + test_ws + test_e2e)"
cd "$BACKEND"
python3 -m pytest \
  tests/test_sprint1_verification.py \
  tests/test_rate_limiting.py \
  tests/test_ws_resilience.py \
  tests/test_e2e_training_flow.py \
  --base-url "$QA_BACKEND_URL" \
  -v --tb=short 2>&1 | tail -80

log "Re-verification complete"
