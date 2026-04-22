# Release Notes — v2.0.0

> **Cut date**: 2026-04-22
> **Base**: v1.0.0 (`547ff663`)
> **Target**: `f0290ac9` on `github/v2.x-prep`
> **QA**: 5/5 sprint regression PASS

## Overview

v2.0.0 is the second major release. Where v1 locked down the physics port and built a unified dashboard around a single algorithm (PPO) + single policy (MLP) + single shaped-reward function, **v2 opens the algorithm matrix**. You can now choose from rule-based ladder or self-play as the opponent, three reward functions, two policy architectures, and three algorithms (PPO, SAC, Dreamer V3). Every selector defaults to v1 behavior so existing workflows are preserved — pick v2 features when you want them.

## Major features

### 1. Self-play League (Sprint 1)

A persistent pool of trained checkpoints that play each other and rank by Elo. Your new run can train against the Rule-based ladder (v1 behavior, default) or sample opponents from the league (uniform / Elo-biased / always-champion). Admission to the pool requires clearing a +25 Elo gate above the pool median. Legacy v1 checkpoints are seeded at Elo 1000 with a `v1_legacy` badge. Live standings broadcast via WebSocket; `/runs/{title}` exposes a League sub-tab with top-10, recent matches, and an Elo line chart.

### 2. Reward model selector (Sprint 2)

`shaped_v1` keeps the v1 nine-term reward (default — no behavior change). `sparse_v1` strips all shaping down to ±1 terminal + ±0.1 per-point for maximum faithfulness to the objective. `learned_shaped_v1` keeps the sparse terminal and adds an IRL-learned shaping term (Stage 2 Phase). Selector exposed on the Hyperparameter form; a chip appears on the run list so you can scan which reward shape each run used.

### 3. LSTM recurrent policy (Sprint 3)

Add a recurrent head to the policy via SB3-contrib's `RecurrentPPO`. Hidden size 256, single LSTM layer on top of the feature extractor. Useful when the agent needs short-term memory of ball trajectory beyond what the stacked observations give. Default remains `mlp_v1` — no regression vs v1.

### 4. SAC-Discrete algorithm (Sprint 4)

Off-policy twin-critic actor-critic with entropy auto-tuning, adapted to the discrete action space. Faster wall-clock per sample than PPO on certain workloads; different exploration profile. Selectable alongside the existing PPO (default). Note: the `sac × lstm_v1` combination is out of scope for this release.

### 5. Dreamer V3 world-model (Sprint 5, Experimental)

A model-based RL algorithm — the agent learns an internal world model and plans through it. Lands as a third algorithm choice alongside PPO and SAC. The v2.0 release tags this Experimental: sample efficiency is validated vs PPO-shaped baseline, but long-horizon stability is not yet characterized. GPU is recommended.

## Migration

For the complete, step-by-step guide, see [docs/migrations/v1-to-v2.md](../migrations/v1-to-v2.md). Short version:

- **Default-safe**: skipping migration works. All new fields default to v1 values; existing runs continue to work unchanged.
- **One-shot backfill** (optional, recommended for a clean `/runs` list):
  ```bash
  docker compose exec backend python -m backend.scripts.migrate_games_bot_level --mode=v1-to-v2-defaults
  docker compose exec backend python -m backend.scripts.seed_league_from_v1_models
  ```
- **Checkpoint compatibility**: PPO `.zip` checkpoints load fine in both PPO and SAC runtimes. MLP ↔ LSTM cross-load is **not supported** — architectures differ. Dreamer V3 uses a distinct `.pt` state_dict and cannot be cross-loaded with SB3 algorithms either direction.
- **WS payload**: v1 clients talking to v2 backend continue to work (they ignore new fields). v2 clients talking to v1 backend see None for the new selectors — the UI renders a dash in that case.

## Known limitations

- **Dreamer V3 is Experimental.** Long-term stability is uncharacterized; GPU strongly recommended. Do not use as the sole algorithm for a production-facing run yet.
- **LSTM × SAC is not supported.** The schema accepts both (`policy_type=lstm_v1, algorithm=sac`) but runtime will fail. Deferred to v2.1+.
- **Dreamer checkpoints are isolated.** They enter the League with a distinct source tag and cannot be Elo-compared directly against PPO/SAC (different action semantics through the world-model). Mixed-algorithm league ranking is a v2.x+ topic.
- **Updating overlay fallback.** If a BE emits gradient-phase WS events inconsistently, the FE falls back to heuristic frame-stall detection. No known cases in v2.0; kept as belt-and-suspenders.

## Screenshots

> QA artifact directory: `docs/qa-reports/v2.0-screenshots/` (populated by QA prior to prod promote).
>
> Placeholder slots:
> - `league-sub-tab.png` — Top-10 pool + recent matches + Elo line
> - `hyperparam-form-s1-s5.png` — Opponent section + reward/policy/algorithm selectors
> - `run-list-chips.png` — algorithm / reward / policy chips inline on the run list
> - `updating-overlay.png` — PPO gradient phase overlay
> - `eval-panel-split.png` — vs Rule ladder vs Top-N League two-card view

## Acknowledgements

- **AI Engineer** — 5 sprint model/algorithm implementations (S1 OpponentProvider + S2 reward enum + S3 LSTM + S4 SAC + S5 Dreamer)
- **Backend Engineer** — WS→manager→run doc field threading across all 5 sprints, league repository, admission callback, migration scripts
- **Frontend Engineer** — HyperparamForm selectors, /runs League sub-tab, updating overlay, run-list chips
- **Designer** — reward/policy selector UX specs + updating overlay spec
- **DevOps** — watchdog for gradient-phase false positives, rebase flow documentation through S3-S5 trainer.py conflicts
- **QA** — 5/5 sprint regression pass, boundary contract verification, VecEnv shape bug catch on Dreamer
- **Product Manager** — sprint boundary coordination, rebase conflict call-outs, v1-to-v2 default preservation gate

## References

- [CHANGELOG.md § 2.0.0](../../CHANGELOG.md#200---2026-04-22)
- [docs/migrations/v1-to-v2.md](../migrations/v1-to-v2.md)
- [docs/retrospective/v2.x-retrospective.md](../retrospective/v2.x-retrospective.md)
- ADRs: [0014](../adr/0014-self-play-league.md), [0015](../adr/0015-reward-simplification.md), [0016](../adr/0016-lstm-recurrent-policy.md), [0017](../adr/0017-sac-continuous-actor-critic.md), [0018](../adr/0018-dreamer-v3-world-model.md)
- Prior release: [v1.0.0](../RELEASE-NOTES-v1.0.0.md)
