# ADR 0017 — SAC actor-critic (v2.x Sprint 4)

**Status:** proposed · **Date:** 2026-04-22

**Context:** S1/S2/S3 on dev. Roadmap priority #4 — alternative
algorithm so sample-efficiency hits a wider surface than on-policy
PPO. Code-free per PM.

## 1. Motivation

PPO is on-policy and discards rollouts per update. At ~1.5M L3
steps `ep_rew_mean` still trends up but `winrate_vs_L3` flattens
near 0.62 (same plateau as ADR 0016). PPO compounders: (a) entropy
collapses fast on shaped_v1 → agent exploits stall-rallies; (b)
rare terminals in sparse_v1 / learned_shaped_v1 barely move the
gradient before rollout discard. SAC addresses both — replay keeps
transitions valuable, α auto-tune keeps exploration alive through
flat-reward regions.

## 2. Discrete vs continuous action space

Current env: `Discrete(12)` = 3 x_dir × 2 y_dir × 2 power_hit minus
redundancies. Engine consumes
`PlayerInput(x_dir∈{-1,0,1}, y_dir∈{-1,0}, power_hit∈bool)` —
discrete is inherited from the physics.js port, not an RL artefact.

- **A — Keep Discrete(12) + SAC-Discrete** (Christodoulou 2019):
  preserves engine, replay msgpack, `LoadedPolicyBot`, ACTION_MAP
  mirror, 22-case parity test. Cost: sb3-contrib 2.8.0 does NOT
  ship it (inventory ARS/CrossQ/MaskablePPO/QRDQN/RecurrentPPO/TQC/
  TRPO) — ~300 LOC vendored + parity tests.
- **B — Re-map to continuous** (Box(3,) for x/y/attack): unlocks
  stock `SAC` / `CrossQ` / `TQC`. Cost: engine consumes floats,
  threshold semantics invented, replay format breaks, S3 MLP/LSTM
  checkpoints unloadable.

**Recommendation: A.** B ripples through every S1–S3 layer; the
vendor is a contained one-time cost. Enum `sac`; `sac_crossq` /
`sac_continuous` reserved for B (no schema churn if it ever wins).

## 3. Boundary contract

Mirrors `reward_model` (ADR 0015) + `policy_type` (ADR 0016). Enum
`algorithm: 'ppo' | 'sac'`, default `'ppo'`; unknown → Pydantic
`payload_invalid`; future additions (`dqn`, `ppo_mask`) extend this
enum, not a new field. Plumbing: `WsTrainingStartPayload.algorithm`
→ `TrainingServiceWrapper.start` → `TrainingManager.start` →
`self._algorithm`, consumed by the run-record writer + factory
dispatcher. `/api/training/runs` + `/runs/{title}` decorate each row
with `algorithm` (legacy default `'ppo'`). **Net-new field** — the
earlier "existing" reference is a misread (`/runs` today carries
only `reward_model` + `policy_type`).

## 4. Algorithm × policy_type × reward_model matrix

`ppo × mlp_v1 × *` and `ppo × lstm_v1 × *` ship (ADR 0016);
`sac × mlp_v1 × *` is the primary S4 target. `sac × lstm_v1 × *` is
**experimental** — SB3 has no `RecurrentSAC` and sb3-contrib has no
recurrent off-policy algo; a GRU head on the SAC actor + recurrent
replay is deferred to S5, factory raises `NotImplementedError`.
`sac × gru_v1 / transformer_v1` inherits ADR 0016's reserved-value
runtime gate. No cross-field WS-layer constraint — runtime-gated in
the trainer (S3 pattern).

## 5. Network architecture

Pinned in `SAC_DEFAULT_KWARGS`, not WS-surfaced: twin Q-critic
(`n_critics=2`) + target nets, Polyak τ=0.005; stochastic actor,
`net_arch=[256,256]` (PPO parity; actor absorbs the entropy head);
α auto-tuned (`ent_coef="auto"`), target entropy `-log(12)` per
Christodoulou §3.1; replay 1M transitions, `learning_starts=10_000`,
`train_freq=1`, `gradient_steps=1`, `batch_size=256`.

## 6. Training metrics / success criteria

Matched-step on `bot_ladder L3` + `shaped_v1`: **sample-efficiency
(primary)** SAC reaches PPO's 1M-step `winrate_vs_L3` in ≤ 700k
steps (30% saving); **final-quality** at 1M steps, `winrate_vs_L3`
≥ PPO; **wall-clock** ≤ 2× PPO on the 4070 Ti. Miss two → SAC
stays opt-in; default stays `ppo`. Eval scorecard reuses S3 columns
(`winrate_vs_L3`, `inference_ms_per_step`, `long_rally_success_rate`).

## 7. Implementation plan

`policy_factory.py` grows an `algorithm` axis:
`make_policy_spec(algorithm, policy_type, net_arch)`. PPO path
unchanged; `sac × mlp_v1` → vendored `SACDiscrete` in a new
`backend/rl/sac_discrete.py` (Christodoulou 2019 on the SB3 `SAC`
base). `trainer.py` dispatches SAC's `.learn()` lifecycle (replay
owned by the model, no rollout buffer); `learning_starts` warm-up
means `MetricsCallback` treats pre-warmup steps as zero-reward so
the plateau detector doesn't trip. `LoadedPolicyBot` gains an
`algorithm` field parallel to `policy_type`, branching `SAC.load`
vs `PPO.load` / `RecurrentPPO.load` at checkpoint-open.

## 8. UI impact

`HyperparamForm` has NO `algorithm` selector today (verified
2026-04-22). Add one styled identical to S2/S3 selectors — default
`ppo`, chip `"PPO"` / `"SAC"`. Designer handoff follows this ADR.
`HyperparamsSummary` gains an Algorithm row; runs-table column TBD
— three enum chips are already dense, a fourth may need layout work.

## 9. Migration

One-shot Mongo backfill `algorithm = "ppo"` on pre-S4
`training_runs` + `league_checkpoints`, idempotent `$exists:False`,
runs alongside S2/S3 backfills at lifespan startup. **Replay buffer
NOT portable across algorithms** — PPO rollouts vs SAC replays have
incompatible shapes; cross-load must fail at SB3 unpickle, enforced
via `algorithm`-gated dispatch in `LoadedPolicyBot._load` + trainer
resume. Checkpoint filenames unchanged — SB3 writes the algo class
into the zip's `data` key so `{slug}__{exp8}__final.zip` keeps working.

**Open:** (1) `SACDiscrete` test budget — 15 cases (S3 symmetry)
vs 8-case smoke — proposed 15; (2) expose `ent_coef` override on WS
or keep auto-only — proposed auto-only for v2.x. **Refs:** Haarnoja
2018 (SAC); Christodoulou 2019 (SAC for discrete actions); SB3
`SAC`; sb3-contrib `CrossQ` (§2 fallback-B).
