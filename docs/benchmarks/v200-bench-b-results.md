# v2.0.0 bench-B — Dreamer V3 @ 2M Results (Investigation Stage)

**Status:** **BLOCKED — approval required before execution**
**Date:** 2026-04-23 · **Branch:** `benchmarks/v200-bench-b-results`
**Owner:** Evaluator · **Training exp8:** `3cb6ffd9` · **Refs:** ADR 0018 §9,
plan `benchmarks/v200-dreamer-plan@4076129b`, release v2.0.0 `ed9348c6`.

## 1. What exists

- bench-B training artifacts at
  `~/.claude-squad/worktrees/bench/v200-dreamer/models/bench/B/3cb6ffd9-…/`:
  - 20 intermediate checkpoints `__100000.zip` … `__2000000.zip` (100k cadence).
  - 1 alias `__final.zip` (2M step, 29.9 MiB, mtime 2026-04-23 08:48).
- All 21 filenames end `.zip` per the ADR 0018 §10 naming contract
  (`{slug}__{exp8}__{step|final}.zip`), but **internals are torch pickle**
  (`th.save(payload, buf)`), not SB3 zip layout.

## 2. Blockers (must resolve before any eval fires)

### B1 — evaluator harness cannot load Dreamer checkpoints

`backend/rl/evaluator.py::ModelEvaluator.evaluate` hardcodes:

```python
from stable_baselines3 import PPO
...
model = PPO.load(model_path)
```

Smoke test against `bench-B__3cb6ffd9__final.zip`:

```
PPO.load FAILED: AssertionError('No data found in the saved file')
```

Dreamer's `DreamerAgent.load(path, env=...)` exists in
`backend/rl/dreamer_runner.py` (line 566), and `LoadedPolicyBot.__init__` on
line 155 already dispatches `algorithm=='dreamer_v3'` → the SAC/PPO/Dreamer
routing pattern is in place for the bot wrapper but **not** for the evaluator.
Running `batch_evaluate` against any bench-B checkpoint will fail on match #1.

### B2 — `batch_evaluate` CLI has no `--seeds` flag

Current CLI (`backend/rl/batch_evaluate.py` lines 195-224) accepts `paths`,
`--levels`, `--n-games`, `--workers`. The PM dispatch assumes
`--seeds 101 102 103 104 105`; that argument does not exist. The
rule-based bot is deterministic and `model.predict(..., deterministic=True)` is
fixed by policy weights, so without Python-level seeding wired through
`env.reset(seed=…)` + model sampling, the 5 "seeds" collapse to 5 identical
runs of the same 100 games. No statistical signal beyond `n_games=500`.

### B3 — runtime + GPU-contention budget check

Per-step cost estimate on 4070 Ti: PPO MLP predict ≈ 1.5 ms; Dreamer RSSM
step ≈ 4-8 ms (not yet measured). Budget:

| scope                           | matches | est. single-worker | 5 workers* |
|---------------------------------|--------:|-------------------:|-----------:|
| Final only, L1/L3/L5, n=100×5   |   1,500 |     ~4-6 h         |   ~50-80 min |
| Curve 5 points × above          |   7,500 |    ~20-30 h        |     ~4-6 h |

*Workers share the 4070 Ti; VRAM headroom is tight after Dreamer model load
(replay buffer dropped on eval but RSSM + actor + critic retained).

## 3. PPO shaped_v1 baseline search (not yet executed)

Plan: query Mongo `runs` collection directly (not via dev HTTP — test
isolation rule, 2026-04-12) for
`{algorithm: 'ppo', reward_model: 'shaped_v1', total_timesteps: {$gte: 1_000_000}}`,
order by `winrate_vs_L3` desc, pick the leader's `final.zip`. Requires:

- Mongo connection string for dev (read-only credential).
- Confirmation that reading `runs` from dev Mongo does not violate the
  2026-04-12 test-isolation directive. Read-only, no WS, no HTTP to dev BE
  — arguably compliant, but PM should ack.

## 4. Proposed fix path (awaiting approval)

1. **Evaluator dispatch** — mirror `LoadedPolicyBot` pattern. Add `algorithm`
   param to `ModelEvaluator.evaluate` (default `'ppo'` for back-compat) and
   `batch_evaluate` CLI; dispatch `DreamerAgent.load(path, env=…)` /
   `SACDiscrete.load` / `PPO.load`. `DreamerAgent.predict` already implements
   the `_PolicyLike` protocol. ~60 LOC + test. Lands on this branch.
2. **Seed wiring** — extend CLI `--seeds` (list of ints, default `[0]`) and
   thread to `env.reset(seed=…)` + torch/numpy RNG at the start of each
   game block. ~20 LOC.
3. **Determinism audit** — run final checkpoint × (seed 101 vs 102) × 10
   games to confirm seed actually diverges trajectories before committing
   to the full 5×100×3×5 grid.
4. **Scope cut options** — if GPU time is scarce: (a) drop curve to 3 points
   (100k / 1M / 2M), (b) drop `--seeds` to `[101, 102, 103]`, (c) evaluate
   on CPU and let the 4070 Ti stay free for Config A prep.

## 5. Primary §9 verdict — **ambiguous, not yet measured**

Cannot assert success or failure of the ADR 0018 §9 sample-efficiency claim
without (B1) fix + actual evaluation. Current verdict: **pending unblock**.

## 6. Next-step proposals (PM pick one)

1. **Approve (B1)+(B2) evaluator patches on this branch** → run final 2M
   (~80 min) first → review → decide on 5-point curve.
2. **Skip curve, ship final-only assessment against a PPO baseline** → find
   best existing `shaped_v1` PPO via Mongo query, run both through patched
   evaluator, produce a quick §9-matched head-to-head. ~2 h total.
3. **Defer everything, start Config A 10M PPO training** — per plan §2 the
   baseline is missing anyway; running A now uses the 48h wall-clock to
   produce the comparison target while B's harness is being fixed.

---
**No code changed, no training kicked, no evaluations run.** This commit
documents the investigation and blockers only.
