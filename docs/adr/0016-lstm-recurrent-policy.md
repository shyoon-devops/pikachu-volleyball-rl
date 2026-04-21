# ADR 0016 — LSTM recurrent policy (v2.x Sprint 3)

**Status:** proposed · **Date:** 2026-04-21

**Context:** S1 self-play + S2 reward_model on dev. Roadmap priority
#3 — recurrent policy so the agent can integrate over rally history
rather than react to the instantaneous 18-float obs. Code-free per
PM; implementation ADR follows sign-off.

## 1. Motivation

`MlpPolicy` sees only the instantaneous 18-float obs. Partial-obs
costs: (a) the previous bounce's rising-vs-falling arc is only
legible through a single `ball.vy` sign flip, (b) opponent intent
over N frames is invisible, (c) wind-up → power-hit timing collapses
to a reflex. S2 shaped_v1 + self-play runs plateau near 0.62
L3-winrate after ~1.5M steps while mean-reward still trends up — an
observability wall, not an optimisation wall.

## 2. Architecture options

- **A — SB3 `RecurrentPPO` / `MlpLstmPolicy`** (sb3-contrib): drop-in
  PPO replacement, `RecurrentRolloutBuffer`, community-maintained.
- **B — GRU** via contrib: fewer params, ~1.3× faster, small
  representational gap on 100+ frame rallies.
- **C — Transformer small head**: strongest on long horizons; 5-10×
  inference latency blows the dashboard render budget.

**Recommendation: A.** Enum = `lstm_v1`; `gru_v1`/`transformer_v1`
reserved for later sprints (no schema churn).

## 3. Boundary contract

Mirrors `reward_model` from ADR 0015:

- Enum `policy_type: 'mlp_v1' | 'lstm_v1' | 'gru_v1' | 'transformer_v1'`.
- `WsTrainingStartPayload.policy_type`, default `'mlp_v1'`. Unknown →
  `ValidationFailure`. `gru_v1`/`transformer_v1` reserved — schema
  accepts them, `TrainingManager.start()` raises `NotImplementedError`.
- `/api/training/runs` response carries `policy_type` per record.
- LSTM hyperparameters pinned for first release as
  `LSTM_POLICY_KWARGS = {lstm_hidden_size=128, n_lstm_layers=1,
  shared_lstm=False, enable_critic_lstm=True}`; override surfacing
  out-of-scope for v2.x.

## 4. Model surgery

- Cross-arch checkpoint load NOT supported — MLP ↔ LSTM fails at
  layer-shape mismatch and must stay that way (silent weight-ignore
  would corrupt training).
- Obs space `Box(18,)` + action space `Discrete(12)` UNCHANGED.
  League pool entries from pre-LSTM checkpoints stay loadable via
  `policy_type`-gated dispatch (`PPO.load` vs `RecurrentPPO.load`).
- New module `backend/rl/policy_factory.py` owns dispatch:
  `policy_type` → `(algo_class, policy_class, policy_kwargs)`.
  `trainer.py` imports the factory; SB3 class names don't leak.

## 5. Training metrics

Eval scorecard gains three Sprint-3 columns:

- `winrate_vs_L3` over 25 matches (primary success gate).
- `inference_ms_per_step` over 10k steps on the eval box (latency gate).
- `long_rally_success_rate` — fraction of >100-frame rallies the
  agent scores (stall-behaviour gate).

MLP baseline (`shaped_v1` + `bot_ladder` L3) and LSTM candidate train
matched `total_timesteps`; diff feeds §6.

## 6. Success criteria

Promote to "usable" iff (at least one of: `winrate_vs_L3` ≥ **+5 pp**
over MLP baseline at matched steps, OR `long_rally_success_rate`
≥ **+30%** relative) AND `inference_ms_per_step < 5 ms` on GPU (3×
the observed MLP ~1.6 ms budget). Miss either gate → LSTM stays
opt-in; default remains `mlp_v1`.

## 7. Sequence handling

- Episode boundary → hidden state reset via `RecurrentRolloutBuffer`
  on `dones=True`; rely on sb3-contrib not reimplement.
- VecEnv independence: each sub-env carries its own hidden slot;
  `DummyVecEnv` and `SubprocVecEnv` both honour this with no layer
  change.
- `LoadedPolicyBot.predict` becomes stateful for LSTM opponents:
  caches `(hidden, cell)` across `get_action` within a match,
  resets via the existing `reset_history` hook. The bot gains a
  `policy_type` field to pick the right `predict()` overload.
- WS `training:update_start/_end` (Fix A) stay correct — extra
  inference lives inside `collect_rollout`, not `train()`.

## 8. UI impact

- Designer adds a `policy_type` selector to `HyperparamForm`, styled
  identically to `reward_model`. Default `mlp_v1`; reserved values
  disabled with a "coming later sprint" tooltip.
- Matrix = `algorithm × policy_type × reward_model`, no cross-field
  constraints; trainer raises `NotImplementedError` at runtime for
  reserved `policy_type`.
- Runs table gains a human `policy` column (`"MLP"` / `"LSTM"`).

## 9. Migration

- One-shot Mongo migration backfills `policy_type = "mlp_v1"` on
  pre-Sprint-3 `training_runs`. Idempotent; mirrors ADR 0015's
  `backfill_training_runs_reward_model` pattern.
- Default change forbidden — callers that omit the field keep MLP.
  Feature flag IS the enum; no separate global flag.
- `LeagueCheckpoint` rows need `policy_type` so `LoadedPolicyBot`
  picks `PPO.load` vs `RecurrentPPO.load`; backfill `"mlp_v1"` on
  pre-Sprint-3 entries at the repository-migration layer.

---

**Open:** (1) expose `lstm_hidden_size`/`n_lstm_layers` on WS payload
in S3 or defer to "advanced hyperparams" — proposed defer; (2) per-
opponent 20 ms/step latency cap on `LoadedPolicyBot` with
`FixedBot(L1)` fallback — proposed yes.
**Refs:** sb3-contrib `RecurrentPPO` / `MlpLstmPolicy`; Hausknecht &
Stone 2015 (DRQN); OpenAI Five 2019 (LSTM for partial obs).
