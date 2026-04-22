# ADR 0014 — Self-play League (v2.x Sprint 1)

**Status:** Accepted
**Date:** 2026-04-20
**Related commits:** S1 AI+BE+FE 22 commits ending `d9099ef4` (merge), hotfix `7e209baf`, opponent interop `ed96b334`, updating overlay `2a0b244d` / `19f29fc8` / `0eb0c8ea`, episode fix `5f23c299`
**Supersedes:** nothing (new subsystem)

## Context

Through v1.0 every RL run trained against the hand-coded Rule-based Bot (L1~L5). This ceiling the policy at "beats L5 consistently" and provides no self-improvement signal beyond that. Modern competitive training uses **self-play** — the agent trains against past versions of itself, forming a population whose strength grows monotonically.

We also lacked a persistent **opponent registry** across runs. Checkpoints were per-experiment, not comparable, and the Rule-based ladder was the only shared benchmark. A standings-tracked league of model versions is required before any serious multi-agent feature.

## Decision

Ship a self-play league as the first v2 deliverable:

### 1. Opponent interface (AI track)

- **`backend/rl/opponent.py`** — `OpponentProvider` protocol: `sample_opponent()` returns a policy callable. Three impls: `RuleBot` (legacy wrapper), `LoadedPolicyBot` (wraps SB3 PPO checkpoint), `LeagueSampler` (rating-biased sampling from registry)
- **Path-traversal hardening** — checkpoint paths validated against `models/` root; broken entries pruned on resample
- **Pydantic interop** — rating via `LeagueCheckpoint.elo`, build via `source + path`

### 2. League registry (BE track)

- **`backend/app/models/league.py`** — `LeagueCheckpoint` / `LeagueMatch` / `LeagueStandings` Pydantic models
- **`backend/rl/elo.py` extended** — K-anneal + anchor pinning (anchors L1=600, L3=900, L5=1200 never change; new entries seed at 1000)
- **`backend/app/services/league_repository.py`** — Motor-backed `manifest.json` + Mongo sync, `/api/league/standings`, `/api/league/checkpoints/{sha}`
- **`backend/rl/league_callback.py`** — match aggregation per N episodes, broadcasts via `training:league_update`
- **`backend/rl/league_admission.py`** — admit to league only on +25 Elo gate above current pool median
- **One-shot migration** (`dafe7b4e`) — `scripts/seed_league_from_v1_models.py` seeds from existing `models/<exp>/*.zip` with `source="v1_legacy"` + `elo=1000.0` seed

### 3. Training integration

- **`training:start`** payload extended with `training_mode: "rule_ladder" | "self_play"` + `sampling: "uniform" | "elo_biased" | "champion"`
- **`TrainingServiceWrapper.start()`** accepts and propagates both fields (hotfix `88208f3c`)
- **Episode counting preserved** in self_play mode (`6e8596ed`) — `info['episode']` propagation unchanged

### 4. FE surface

- **HyperparamForm Opponent section** — segmented control (Rule ladder / Self-play) + sampling radio + pool size chip
- **/runs/{title} League sub-tab** — pool status + top-10 + recent matches + Elo line chart
- **Recent Games** — opponent column + current run Elo badge
- **Evaluation panel split** — 2 cards: vs Rule ladder (existing E1-E10) + vs Top-N league (new)

### 5. Updating overlay

During PPO gradient phase training is paused from the env's perspective (no new frames). We introduce explicit `training:update_start` and `training:update_end` WS events so FE shows an "updating…" overlay instead of appearing frozen. Heuristic fallback (frame-stall detection) kept as safety.

## Consequences

### Positive

- **Self-improvement ceiling removed.** League matches generate signal above L5, provided the admission gate is calibrated
- **Cross-run comparability.** Every checkpoint has an Elo rating on the same scale, including legacy v1 models
- **Auditable standings.** Pool state persists in MongoDB, WS broadcasts live updates, REST exposes full history
- **Anchor corridor preserved.** Rule-based L1/L3/L5 are never rated; they stay as absolute reference points

### Negative / costs

- **Training cost up.** Self-play needs both current policy + sampled opponent in memory, ~1.5x the PPO cost
- **Cold-start problem.** An empty league at epoch 0 — addressed by the v1.0.0 migration that backfills from existing checkpoints
- **Farming vector.** A near-anchor rating can be gamed by selectively matching weak opponents — mitigated by +25 Elo admission gate and uniform sampling option

### Enforcement

- All new multi-agent features must extend the `OpponentProvider` interface, not add parallel mechanisms
- Checkpoint admission must pass through `LeagueAdmissionCallback` — no direct registry mutation

## References

- Design spec: `docs/design/UPDATING-OVERLAY.md`
- Migration script: `backend/scripts/seed_league_from_v1_models.py`
- Prior reward work: [ADR 0003](0003-rl-reward-rebalance.md)
- Port parity contract (engine unchanged): [ADR 0011](0011-faithful-port-with-parity-test.md)
