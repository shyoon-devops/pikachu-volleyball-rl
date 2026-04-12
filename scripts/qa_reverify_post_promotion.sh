#!/usr/bin/env bash
# QA re-verification after dev→QA promotion (2026-04-12).
#
# Before rebuild — baseline captured:
#   QA backend image SHA: sha256:dab203bf580e72cc5...
#   QA frontend bundle:   assets/index-we-0u1Nl.js (839199 bytes)
#   QA frontend ETag:     "69db3c8d-cce1f"
#   Start button state:   DUPLICATE (TrainingControls "Start" + HyperparamForm "Start Training")
#
# PM promotion checklist:
#   1. New frontend bundle hash at http://192.168.0.248:3001/
#   2. All 4 backend suites pass (expected 48 pass / 0 fail / 3 skip)
#   3. Deterministic fails resolved (/api/models probes in test_burst_triggers_429)
#   4. Rate-limit exemption verified (/api/health 200-burst = 0x429, 0x5xx)
#   5. Duplicate Start button removed (count of `children:\`Start\`` goes 1 → 0)
#
# Usage:
#   bash scripts/qa_reverify_post_promotion.sh 2>&1 | tee /tmp/qa_reverify_$(date +%s).log

set -u  # Don't set -e — we want to collect all results, not abort on first fail

REPO=/home/yoon/.claude-squad/worktrees/yoon/qa-engineer_18a54a027720e006
BACKEND=$REPO/backend
QA_BACKEND_URL=http://localhost:8002
QA_FRONTEND_URL=http://192.168.0.248:3001

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
# 4. Rate-limit exemption on /api/health
# ---------------------------------------------------------------------------
log "Step 4 — /api/health rate-limit exemption (200-request burst)"
python3 - <<EOF
import asyncio, httpx
async def main():
    async with httpx.AsyncClient(base_url="$QA_BACKEND_URL", timeout=15) as c:
        results = await asyncio.gather(
            *[c.get("/api/health") for _ in range(200)],
            return_exceptions=True,
        )
    codes = [r.status_code for r in results if not isinstance(r, Exception)]
    c200 = codes.count(200); c429 = codes.count(429)
    c5xx = sum(1 for x in codes if x >= 500)
    print(f"200x{c200}  429x{c429}  5xxx{c5xx}")
    if c429 == 0 and c5xx == 0 and c200 >= 190:
        print("\033[32m✅ exemption verified\033[0m")
    else:
        print("\033[31m❌ exemption broken\033[0m")
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
