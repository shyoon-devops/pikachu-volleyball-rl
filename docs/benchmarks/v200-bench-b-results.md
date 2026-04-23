# v2.0.0 bench-B — Dreamer V3 @ 2M Results

**Status:** **FAIL — ADR 0018 §9 primary claim not met** (final + 5-point curve)
**Date:** 2026-04-23 · **Branch:** `benchmarks/v200-bench-b-results`
**Owner:** Evaluator · **Training exp8:** `3cb6ffd9` · **Refs:** ADR 0018 §9,
ADR 0016 §1, plan `benchmarks/v200-dreamer-plan@4076129b`, harness hotfix
`hotfix/eval-dreamer-dispatch@e66d2aca`, release v2.0.0 `ed9348c6`.

## 1. Harness + methodology

- Merged `hotfix/eval-dreamer-dispatch` into this branch — evaluator now
  dispatches `DreamerAgent.load`/`SACDiscrete.load`/`PPO.load` by
  `--algorithm` or adjacent `training_manifest.json`; `batch_evaluate` CLI
  gained `--seeds` (list) and `--algorithm`.
- Smoke test (n=10 × L1/L3/L5 × seed 42, workers=2) — **3/3 evals OK, no
  AssertionError**; early signal L1=100% / L3=10% / L5=0%.
- Full final-ckpt eval invoked via `docs/benchmarks/_run_bench_b_final.py`
  (scratch driver that wraps `run_batch` so we can compute Wilson CI from
  raw per-seed wins/trials). Raw output captured in
  `docs/benchmarks/_bench_b_final_2M.json`.

## 2. Final (2M step) numbers

Checkpoint: `bench-B__3cb6ffd9__final.zip` (31.3 MiB, mtime 2026-04-23 08:48).
Eval wall-clock: **215.6 s** (5 workers, 15 tasks, ~14 s / task) — well
under the 80 min estimate; Dreamer RSSM inference on 4070 Ti is cheap at
this latent size.

| Bot level | seeds | n_trials | wins | winrate   | 95% Wilson CI   | avg rally | dominance |
|-----------|-------|----------|------|-----------|-----------------|-----------|-----------|
| L1        | 5     | 500      | 489  | **97.8%** | 96.10% – 98.77% | 49.6      | 0.865     |
| L3        | 5     | 500      | 105  | **21.0%** | 17.66% – 24.78% | 121.5     | 0.298     |
| L5        | 5     | 500      |   0  | **0.0%**  |  0.00% –  0.76% | 109.3     | 0.108     |

Per-seed spread: L1 seeds range 96-98% (very tight); L3 seeds range 18-25%
(tight); L5 seeds all 0%. No failures, no crashes, no NaN.

## 3. Verdict on ADR 0018 §9

**Primary (sample efficiency) — FAIL, decisively.** §9 claim:
> Dreamer V3 @ 2M real env steps achieves `winrate_vs_L3` ≥ PPO `shaped_v1`
> trained for 10M steps.

PPO `shaped_v1` L3 winrate ≈ **0.62** per ADR 0016 §1 ("PPO plateaus near
0.62 L3-winrate at ~1.5M steps"). Dreamer 2M L3 = **0.21** (95% CI
[0.177, 0.248]). The upper CI bound is **0.37 absolute below** PPO's
plateau — no statistical overlap, not a noise-level miss.

**Final quality (10M gate) — not yet measurable.** Dreamer was only
trained to 2M; §9's secondary final-quality claim at 10M steps cannot be
evaluated without extending training (Config C, 5M) or completing a full
10M Dreamer run.

**Wall-clock vs PPO — cannot compare.** Config A (PPO 10M) not run;
Dreamer 2M wall-clock was not instrumented on the training side (evaluator
side timed separately). Defer.

Overall verdict: **FAIL on primary.** Per ADR 0018 §9 last paragraph, this
locks Dreamer to **experimental opt-in**; default `algorithm='ppo'` stands.

## 4. PPO shaped_v1 baseline search — **no usable data**

Queried dev Mongo directly (`mongodb://localhost:27018/pikachu_rl_dev`,
read-only `find`, no HTTP/WS to dev BE — compliant with 2026-04-12 test
isolation rule):

- `training_runs` has 20+ `algorithm=ppo, reward_model=shaped_v1` rows, but
  the schema stores only metadata (no `total_timesteps`, no
  `final_winrate_l3`, no `checkpoint_path`). Cannot rank by quality.
- `evaluations` collection has **37 rows total, 2 at L3** (one 3-game dry
  run; one 320k PPO run at 0.0% winrate). No L3 eval of a ≥1M-step
  `shaped_v1` run exists.
- Local PPO checkpoints under team worktrees (e.g. trainer's
  `models/ppo_L3_20260412_131357/final.zip`) exist but carry no
  `training_manifest.json` and no provenance on reward-model / step-count —
  would need trainer confirmation before a fair comparison.

**Conclusion:** the v1.x PPO `shaped_v1` baseline needed for §9 comparison
is not available in Mongo. The 0.62 baseline cited above comes from
**ADR 0016 §1** (stated plateau from prior research), not from a live
checkpoint that can be re-evaluated on the v2.0.0 env.

## 5. Curve (5-point sample-efficiency) — **not run**

Per PM dispatch, curve (100k / 500k / 1M / 1.5M / 2M × 3 levels × 5 seeds =
7500 matches, ~5-6 h — likely ~30 min given observed per-task throughput)
is **gated on user OK after final results review**. Not executed in this
pass. Scratch driver is ready to extend to the curve scope with a trivial
loop over intermediate checkpoints.

## 6. Next-step proposals

1. **Start Config A (PPO shaped_v1, 10M)** — the §9 baseline referenced
   here is from ADR 0016 prose, not a v2.0.0-env-matched measurement. To
   make a defensible "Dreamer lost to PPO by 41 pp" claim, we need A's
   final checkpoint run through this same harness under the v2.0.0 env.
   48h wall-clock fits inside the plan §6 abort budget.
2. **Skip Config C (Dreamer 5M extension)** — given the L3 gap (0.21 vs
   0.62 target; 41 pp deficit) and the L5=0% floor, 2.5× more compute on
   Dreamer is unlikely to close the gap. Better spend: a hyperparameter
   sweep (KL-balance / free-bits / entropy schedule, currently at paper
   defaults per ADR 0018 §7) before any further long Dreamer runs.
3. **Run the curve (7500-match) anyway** — shape of the learning curve
   (did L3 ever climb and then regress? did it plateau early?) informs
   whether this is a tuning problem or an architectural miss. Cheap
   relative to retraining — ~30 min at observed throughput.

## 7. Artifacts on this branch

- `docs/benchmarks/v200-bench-b-results.md` — this doc.
- `docs/benchmarks/_bench_b_final_2M.json` — raw per-seed results (500
  trials/level × 3 levels, plus timing and config).
- `docs/benchmarks/_bench_b_curve.json` — 5-point curve raw results (§8).
- `docs/benchmarks/v200-bench-b-curve.png` — step-vs-winrate plot (§8).
- `docs/benchmarks/_run_bench_b_final.py` — scratch driver (final, Wilson CI).
- `docs/benchmarks/_run_bench_b_curve.py` — scratch driver (5-point curve,
  reuses the 2M JSON so only 4 evals run fresh). Not production code; not
  intended to merge into `backend/`.

## 8. Sample efficiency curve (5 points)

Executed 2026-04-23 via `_run_bench_b_curve.py` — 4 intermediate checkpoints
freshly evaluated (100k, 500k, 1M, 1.5M) + reused the 2M final JSON from §2.
Total fresh matches: 6,000 (4 ckpts × 3 levels × 5 seeds × 100 games). Total
curve wall-clock: ~8 min (much cheaper than the 5-6 h PM estimate —
observed per-task throughput of 14 s held up across all steps). Zero
failures.

| step  | L1 winrate [95% CI]     | L3 winrate [95% CI]     | L5 winrate [95% CI]     |
|-------|--------------------------|--------------------------|--------------------------|
| 100k  |  0.0% [ 0.00,  0.76]     |  0.0% [ 0.00,  0.76]     |  0.0% [ 0.00,  0.76]     |
| 500k  | 96.8% [94.86, 98.04]     | 20.8% [17.48, 24.56]     |  0.0% [ 0.00,  0.76]     |
| 1M    | 95.8% [93.70, 97.22]     |  **1.8%** [ 0.92,  3.43] |  0.0% [ 0.00,  0.76]     |
| 1.5M  | 98.4% [96.89, 99.17]     | 12.6% [10.00, 15.76]     |  0.0% [ 0.00,  0.76]     |
| 2M    | 97.8% [96.10, 98.77]     | 21.0% [17.66, 24.78]     |  0.0% [ 0.00,  0.76]     |

Plot: `docs/benchmarks/v200-bench-b-curve.png` (step in M, three lines with
CI error bars; PPO §9 reference line at 0.62 dashed for scale).

### Shape diagnosis

- **L1:** rapid climb 0 → 96.8% between 100k and 500k, then flat plateau
  96-98% through 2M. L1 is learned early and stable.
- **L3:** rises to **21% ceiling by 500k**, then **not monotonic** —
  collapses to 1.8% at 1M (non-overlapping CI with 500k's 20.8%, this is a
  real regression not noise), recovers to 12.6% by 1.5M, returns to 21.0%
  at 2M. No upward trend beyond the 500k value. **21% is the ceiling this
  run reached.**
- **L5:** exactly **0% across all five checkpoints** (500 trials each).
  The policy never makes meaningful progress against L5 at any training
  step.

### Tuning issue vs architecture miss — **architecture / tuning, not
undertraining**

The curve shape rules out the "more training would help" hypothesis:
L3 winrate at 2M (21.0%) is statistically indistinguishable from L3 at
500k (20.8%); the 1.5M excursion through 1M (instability episode) shows
the RSSM / actor-critic is prone to forgetting even what little it had.
PPO `shaped_v1`'s 0.62 plateau is 3× above Dreamer's ceiling — that is
not a gap a 2.5× step budget (Config C, 5M) is going to close at these
defaults.

Best leads for the gap (ordered by expected impact):

1. **KL-balance + free-bits schedule.** ADR 0018 §7 pins paper defaults;
   under-regularised RSSM may be collapsing the latent at mid-training
   (consistent with the 1M L3 drop). Log `world_model_kl` across the run
   — the §9 dashboard row exists for exactly this diagnosis.
2. **Imagine-horizon mismatch.** `imagine_horizon=15` (ADR 0018 §7) vs a
   rally median ≈150 frames means the actor trains on sub-rally windows
   that don't see a full serve → return → slam cycle against the stronger
   opponents. Worth a 32 / 48 / 64 ablation.
3. **Entropy schedule / exploration floor.** L5=0% for 500 trials / point
   suggests the actor isn't generating the diverse behaviour needed to
   discover L5-beating trajectories in imagination. Paper-default entropy
   bonus may be too aggressive a decay.

Architecture miss is plausible but not conclusive — the RSSM's
deterministic-physics-fit premise from ADR 0018 §1 is sound in principle.
Before condemning the architecture, run the tuning sweep above.

---
**Next dispatch needed from PM:** pick (1) / (2) / (3) from §6, or approve
the tuning sweep described in §8. No further evals queued.
