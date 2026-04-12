#!/usr/bin/env bash
# End-to-end verification of backup + restore flow.
#
# Strategy: do not touch production databases. Spin up a throwaway mongo
# container, seed it with known data, exercise mongodump → mongorestore using
# the same commands as scripts/backup.sh / scripts/restore.sh, and diff the
# before/after to prove the round-trip is lossless. Also verifies the
# model-checkpoint tar archive by unpacking into a tempdir and comparing
# checksums.
#
# Usage:
#   ./scripts/test-backup.sh              # Run full verification
#   ./scripts/test-backup.sh --keep       # Leave the throwaway container up for debugging

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
source "$SCRIPT_DIR/_common.sh"

KEEP=0
for arg in "$@"; do
    case "$arg" in
        --keep) KEEP=1 ;;
        *) echo "unknown arg: $arg"; exit 2 ;;
    esac
done

TEST_CONTAINER="pikachu-backup-test-$(date +%s)"
TEST_PORT="27099"
TEST_DB="pikachu_rl_backuptest"
WORK_DIR="$(mktemp -d -t pikachu-backup-XXXXXX)"

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
pass() { printf "  ${GREEN}[PASS]${NC} %s\n" "$1"; }
fail() { printf "  ${RED}[FAIL]${NC} %s\n" "$1"; FAILURES=$((FAILURES + 1)); }
warn() { printf "  ${YELLOW}[WARN]${NC} %s\n" "$1"; }

FAILURES=0

cleanup() {
    echo ""
    if [ "$KEEP" -eq 1 ]; then
        echo "--- leaving $TEST_CONTAINER up for debugging (--keep) ---"
        echo "  port: $TEST_PORT"
        echo "  workdir: $WORK_DIR"
    else
        echo "--- cleanup ---"
        $DOCKER rm -f "$TEST_CONTAINER" >/dev/null 2>&1 || true
        rm -rf "$WORK_DIR"
    fi
}
trap cleanup EXIT

echo "=== Backup/restore verification ==="
echo "  Test container: $TEST_CONTAINER (port $TEST_PORT)"
echo "  Workdir:        $WORK_DIR"
echo ""

# -----------------------------------------------------------------------------
# Step 1 — spin up throwaway mongo
# -----------------------------------------------------------------------------
echo "[1/6] Starting throwaway mongo container..."
$DOCKER run -d --name "$TEST_CONTAINER" -p "$TEST_PORT:27017" mongo:7 >/dev/null

# Wait up to 30s for mongo to be reachable
for i in $(seq 1 30); do
    if $DOCKER exec "$TEST_CONTAINER" mongosh --quiet --eval 'db.runCommand({ping:1}).ok' 2>/dev/null | grep -q 1; then
        pass "mongo ready (${i}s)"
        break
    fi
    sleep 1
    [ "$i" -eq 30 ] && { fail "mongo failed to start within 30s"; exit 1; }
done

# -----------------------------------------------------------------------------
# Step 2 — seed with known data (2 collections, 3 docs each)
# -----------------------------------------------------------------------------
echo ""
echo "[2/6] Seeding test data..."
SEED_JS='
db = db.getSiblingDB("'$TEST_DB'");
db.games.insertMany([
  {game_id:"t1", score1:15, score2:10, winner:1, duration_frames:4500},
  {game_id:"t2", score1:8, score2:15, winner:2, duration_frames:3200},
  {game_id:"t3", score1:15, score2:13, winner:1, duration_frames:5100}
]);
db.metrics.insertMany([
  {step:1000, mean_reward:0.12, episode:42},
  {step:2000, mean_reward:0.18, episode:84},
  {step:3000, mean_reward:0.24, episode:126}
]);
print("GAMES=" + db.games.countDocuments() + ",METRICS=" + db.metrics.countDocuments());
'
SEED_RESULT=$($DOCKER exec "$TEST_CONTAINER" mongosh --quiet --eval "$SEED_JS" 2>&1 | grep "GAMES=" | tail -1)
echo "  $SEED_RESULT"
if echo "$SEED_RESULT" | grep -q 'GAMES=3,METRICS=3'; then
    pass "seeded 3 games + 3 metrics"
else
    fail "seed verification (got: $SEED_RESULT)"
fi

# -----------------------------------------------------------------------------
# Step 3 — run mongodump (same flags as backup.sh)
# -----------------------------------------------------------------------------
echo ""
echo "[3/6] mongodump → archive (same flags as backup.sh)..."
ARCHIVE="$WORK_DIR/mongo.archive.gz"
$DOCKER exec "$TEST_CONTAINER" \
    mongodump --db="$TEST_DB" --archive --gzip > "$ARCHIVE" 2>"$WORK_DIR/dump.err"

if [ -s "$ARCHIVE" ]; then
    SIZE=$(du -h "$ARCHIVE" | cut -f1)
    pass "dump produced ($SIZE)"
else
    fail "dump produced an empty archive"
    cat "$WORK_DIR/dump.err"
fi

# -----------------------------------------------------------------------------
# Step 4 — drop DB (simulate data loss)
# -----------------------------------------------------------------------------
echo ""
echo "[4/6] Dropping test DB to simulate data loss..."
$DOCKER exec "$TEST_CONTAINER" mongosh --quiet --eval "db.getSiblingDB('$TEST_DB').dropDatabase()" >/dev/null 2>&1

POST_DROP=$($DOCKER exec "$TEST_CONTAINER" mongosh --quiet --eval "db.getSiblingDB('$TEST_DB').games.countDocuments()" 2>&1 | tail -1 | tr -d '\r\n ')
if [ "$POST_DROP" = "0" ]; then
    pass "DB dropped (games count = 0)"
else
    fail "post-drop count should be 0, got: $POST_DROP"
fi

# -----------------------------------------------------------------------------
# Step 5 — restore from archive (same flags as restore.sh)
# -----------------------------------------------------------------------------
echo ""
echo "[5/6] mongorestore from archive..."
cat "$ARCHIVE" | $DOCKER exec -i "$TEST_CONTAINER" \
    mongorestore --archive --gzip --drop --db="$TEST_DB" \
    --nsFrom="${TEST_DB}.*" --nsTo="${TEST_DB}.*" >"$WORK_DIR/restore.log" 2>&1 || {
        fail "restore command exited non-zero"
        tail -20 "$WORK_DIR/restore.log"
    }

# -----------------------------------------------------------------------------
# Step 6 — verify data matches seed
# -----------------------------------------------------------------------------
echo ""
echo "[6/6] Verifying restored data matches seed..."
VERIFY_JS='
db = db.getSiblingDB("'$TEST_DB'");
const g = db.games.findOne({game_id:"t1"}) || {};
const m = db.metrics.findOne({step:1000}) || {};
print("GAMES=" + db.games.countDocuments() + ",METRICS=" + db.metrics.countDocuments() + ",SCORE1=" + g.score1 + ",REWARD=" + m.mean_reward);
'
VERIFY=$($DOCKER exec "$TEST_CONTAINER" mongosh --quiet --eval "$VERIFY_JS" 2>&1 | grep "GAMES=" | tail -1)
echo "    $VERIFY"

if echo "$VERIFY" | grep -q 'GAMES=3,METRICS=3'; then
    pass "document counts restored (3 games + 3 metrics)"
else
    fail "document counts mismatch after restore (got: $VERIFY)"
fi

if echo "$VERIFY" | grep -q 'SCORE1=15,REWARD=0.12'; then
    pass "document values match original seed"
else
    fail "document values do not match seed (got: $VERIFY)"
fi

# -----------------------------------------------------------------------------
# Model tarball round-trip (if models/ exists and non-empty)
# -----------------------------------------------------------------------------
echo ""
echo "--- Model checkpoint tar round-trip ---"
MODELS_DIR="$PROJECT_DIR/models"
if [ -d "$MODELS_DIR" ] && [ -n "$(ls -A "$MODELS_DIR" 2>/dev/null)" ]; then
    TAR_FILE="$WORK_DIR/models.tar.gz"
    tar -czf "$TAR_FILE" -C "$PROJECT_DIR" models/
    pass "tarball created ($(du -h "$TAR_FILE" | cut -f1))"

    EXTRACT_DIR="$WORK_DIR/extracted"
    mkdir -p "$EXTRACT_DIR"
    tar -xzf "$TAR_FILE" -C "$EXTRACT_DIR"

    # Compare checksums of every file under models/
    ORIG_SUM=$(cd "$PROJECT_DIR" && find models -type f -print0 | sort -z | xargs -0 sha256sum | sha256sum | cut -c1-16)
    REST_SUM=$(cd "$EXTRACT_DIR" && find models -type f -print0 | sort -z | xargs -0 sha256sum | sha256sum | cut -c1-16)

    if [ "$ORIG_SUM" = "$REST_SUM" ]; then
        pass "tar round-trip checksum matches ($ORIG_SUM)"
    else
        fail "tar checksum mismatch ($ORIG_SUM vs $REST_SUM)"
    fi
else
    warn "models/ is empty; skipped tar round-trip"
fi

# -----------------------------------------------------------------------------
# Replay preservation (backup.sh does NOT archive replays — confirm this is intentional)
# -----------------------------------------------------------------------------
echo ""
echo "--- Replay backup coverage ---"
if grep -q "replay" "$SCRIPT_DIR/backup.sh" 2>/dev/null; then
    pass "backup.sh mentions replays"
else
    warn "backup.sh does NOT archive replays (msgpack files under replays/)."
    warn "Consider adding a replays tarball step if PM wants them in the retention plan."
fi

# -----------------------------------------------------------------------------
# Summary
# -----------------------------------------------------------------------------
echo ""
echo "=== Verification result ==="
if [ "$FAILURES" -eq 0 ]; then
    printf "${GREEN}All checks passed.${NC}\n"
    exit 0
else
    printf "${RED}%d check(s) failed.${NC}\n" "$FAILURES"
    exit 1
fi
