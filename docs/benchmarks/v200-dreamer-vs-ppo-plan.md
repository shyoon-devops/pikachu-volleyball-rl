# v2.0.0 — Dreamer V3 vs PPO shaped_v1 Benchmark Plan

**Status:** draft (plan-only) · **Date:** 2026-04-17 ·
**Branch:** `benchmarks/v200-dreamer-plan` · **Owner:** Evaluator ·
**Refs:** ADR 0018 §9, ADR 0016 §7, release ed9348c6.

## 1. Hypothesis

ADR 0018 §9 (sample-efficiency, primary): **Dreamer V3 @ 2M real env steps
achieves `winrate_vs_L3` ≥ PPO `shaped_v1` @ 10M steps**, matched on reward
model, obs space, evaluator ladder. Miss → Dreamer stays experimental; default
`algorithm='ppo'` stands.

## 2. Configs

Shared: env `PikachuVolleyballEnv v2.0.0`, `obs_dim=18`, `Discrete(12)`,
`reward_model=shaped_v1`, `training_mode=self_play_with_L3_anchor`,
`sampling=deterministic-eval`, seeds `{101..105}`, `hidden_size=512`.

| id | algorithm  | policy_type      | steps | role                          |
|----|------------|------------------|-------|-------------------------------|
| A  | ppo        | mlp_v1           | 10M   | baseline                      |
| B  | dreamer_v3 | mlp_v1 (ignored) | 2M    | primary §9 claim              |
| C  | dreamer_v3 | mlp_v1 (ignored) | 5M    | extended; run only if budget  |

Dreamer knobs pinned to `DREAMER_DEFAULT_KWARGS` (ADR 0018 §7): RSSM 512,
latent 32×32, imagine_horizon 15, batch 16, seq 64, train_every 16, wm_lr 1e-4,
actor/critic_lr 3e-5. PPO uses ADR 0016 §7 shaped_v1 defaults. No WS overrides.

## 3. Evaluator

Reuse `backend/rl/batch_evaluate.py` unchanged:
`python -m backend.rl.batch_evaluate <ckpt.zip> --levels 1 3 5 --n-games 100 --workers 5`.
5 seeds × 100 games × 3 levels = **1500 matches / eval point**. Per-level
winrate + 95% Wilson CI; writes Mongo `evaluations` (tag
`benchmark=v200-dreamer-vs-ppo`); Elo tracker ingests automatically.

## 4. Execution environment

Dev-server worktree `~/.claude-squad/worktrees/bench/v200-dreamer`. Single
4070 Ti (12 GB) — configs run **sequentially**; DevOps sets
`BENCH_LOCK=v200-dreamer` to pause dev-BE `training:start`. `tmux` detached,
one pane per config; logs → `runs/v200-bench/<id>/trainer.log`; checkpoints
every 100k steps → `models/bench/<id>/`. C starts only after A+B eval-report.

## 5. Metrics

- **Primary:** `winrate_vs_L3` at 2M (B) vs 10M (A).
- **Secondary:** sample efficiency — first step where `winrate_vs_L3 ≥ 0.50`.
- **Tertiary:** wall-clock s/1k env-steps (§9 ≤ 3× PPO); GPU VRAM peak
  (nvidia-smi @ 30s); stalled-rally rate (`rally<3 ball-touches` fraction).

## 6. Abort criteria (any 1 hit → stop that config)

(a) world-model loss NaN before 50k steps (RSSM collapse); (b) CUDA OOM on
4070 Ti; (c) wall-clock > 48h on one config; (d) `winrate_vs_L3` decreasing
across 3 consecutive 100k eval points.

## 7. Reporting

Every 100k steps → `batch_evaluate` → Mongo (tagged), Elo auto-updated. At
2M (B) / 10M (A) / 5M (C) gates, `backend.rl.report_generator` renders
`docs/benchmarks/v200-results.md` (winrate × level × seed with CI bars,
sample-efficiency line, wall-clock + VRAM, stalled-rally rate). Attach to
GitHub Release **v2.0.1** (or `v2.0.1-benchmark` tag-note), cross-linked from
ADR 0018 §9.

**Approval gate:** plan-only commit. PM + Trainer sign-off + DevOps
`BENCH_LOCK` coordination required before any `training:start` for A/B/C.
