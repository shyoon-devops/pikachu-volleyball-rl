# v2.0.0 bench-B — Dreamer V3 @ 2M Results

**Status:** **FAIL — ADR 0018 §9 primary claim not met** (final-ckpt scope)
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
- `docs/benchmarks/_run_bench_b_final.py` — scratch driver (calls
  `run_batch` programmatically + Wilson CI math). Not production code; not
  intended to merge into `backend/`.

---
**Next dispatch needed from PM:** pick (1) / (2) / (3) from §6 or specify
another path. No further evals queued.
