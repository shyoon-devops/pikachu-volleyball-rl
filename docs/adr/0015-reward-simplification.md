# ADR 0015 — Reward simplification (v2.x Sprint 2)

**Status:** proposed
**Date:** 2026-04-19
**Context:** v1.0.0 ships 9 hand-tuned reward terms in
`backend/rl/env.py::_compute_reward` (win/score/timeout + 6 shaping
signals). The shaping is brittle — each new behavior needed a new
heuristic — and introduces two known farming paths (approach +
offensive pressure can be cycled without a scoring event). This ADR
specifies the move to sparse terminal rewards plus a *learned* shaping
term, supersedes ADR 0003's rebalance. Code-free per PM; design only.

## 1. Current reward decomposition

Nine terms, enumerated from `env.py::_compute_reward` docstring:
  1. game outcome ±50, 2. score ±10, 3. rally timeout −12,
  4. touch (+3/+1/−2), 5. net crossing +2, 6. approach +0.02/f,
  7. offensive pressure +0.02/f, 8. ready position +0.005/f,
  9. stall penalty −0.05/f. Contribution audit plan: per-term ablation
(drop one term at a time, train 500k steps vs L1/L3, compare win-rate
and rally-length vs full-shaped baseline). Farming candidates —
#6 (approach) + #7 (pressure) + #8 (ready) run per-frame and can
accumulate without progressing a rally.

## 2. Target reward structures (A / B / C)

- **A — sparse terminal.** Win +1, lose −1, per-point ±0.1. All shaping
  removed. Simplest, most faithful to the gameplay objective, highest
  sample-cost to train from scratch.
- **B — sparse + IRL-learned shaping.** Terminal as in A plus a learned
  potential-based shaping function Φ(s) fitted on demonstrator data
  (MaxEnt IRL or AIRL). Shaping is added as `γ·Φ(s')−Φ(s)` (policy-
  invariant per Ng-Harada-Russell 1999), so the optimal policy is
  identical to A's but gradients are dense.
- **C — sparse + RLHF preference learning.** Terminal as in A plus a
  reward model r̂(s,a) learned from preference pairs. Pairs generated
  scripted initially (e.g. v1.0.0 policy beats L1 rollout preferred
  over the reverse), with a future hook for human preference.

**Recommendation:** **B** for Sprint 2. Closest to spec intent
("학습된 shaping"), policy-invariance theorem keeps the guarantee
that the optimal policy doesn't degrade, and demonstrator data is
already on disk (v1.0.0 checkpoints) — no human labelling required.
C is queued for Sprint 3 if a human-in-the-loop cycle materialises.

## 3. Transition strategy

- New enum field `reward_model: 'shaped_v1' | 'sparse_v1' |
  'learned_shaped_v1'` threaded through `WsTrainingStartPayload`,
  `TrainingManager.start`, and stored on the run record.
- Default `'shaped_v1'` (existing behavior). `'sparse_v1'` and
  `'learned_shaped_v1'` are opt-in.
- Old checkpoints remain loadable — only `_compute_reward` branches
  on the field, the observation space and action space are
  unchanged.
- Parallel-training contract: two trainers can run different reward
  models against the same engine build for A/B comparison; the
  evaluator tags each run's scorecard with its reward model.

## 4. IRL / RLHF implementation

- **Demonstrator data:** 200-500 games of v1.0.0 `final.zip`
  (`models/` v1_legacy pool) vs L3 bot. Saved as msgpack frames
  already; replay them as (s, a) trajectories. No human data for
  Sprint 2.
- **IRL algorithm:** MaxEnt IRL (simpler, closed-form) as the
  baseline; AIRL (adversarial, `stable-baselines3-contrib`) if
  MaxEnt plateaus. Output is Φ(s) implemented as a small MLP
  (same 18-feature obs → scalar).
- **Integration:** new module `backend/rl/reward_irl.py` owns Φ;
  `env._compute_reward('learned_shaped_v1')` calls
  `shaping.delta(prev_obs, curr_obs)` and returns
  `terminal_reward + γ·Φ(s')−Φ(s)`.
- **Training Φ:** offline pre-training before the RL run; Φ weights
  pinned for the full PPO training.

## 5. Engine / parity invariance

- `backend/game/engine.py` and `physics.py` **unchanged**. The
  `test_parity_with_original.py` 22-case suite must stay 22/22
  through every Sprint 2 commit.
- `env._compute_reward` is the only behavioural site. Obs builder
  (`_get_obs`) untouched, so checkpoint weight shapes stay
  compatible across reward-model flips.
- New `reward_irl.py` module is additive; no imports into engine.

## 6. Success metrics

- **Primary:** `sparse_v1` and `learned_shaped_v1` each reach
  ≥ v1.0.0 `shaped_v1` win-rate against L1/L3/L5 on the evaluator
  scorecard within 2× sample budget.
- **Anti-farming:** stalled-rally rate (> RALLY_MAX_FRAMES events /
  1k matches) drops by ≥50% for `sparse_v1` and `learned_shaped_v1`
  vs `shaped_v1`.
- **A/B harness:** the release-gate evaluator produces one
  scorecard per reward model; PM calls the swap when both
  thresholds clear.

## 7. Boundary contract (FE / Designer handoff)

- `WsTrainingStartPayload` gains `reward_model: str` enum field,
  defaulted to `shaped_v1`. Validation rejects unknown values.
- `/api/runs` responses include `reward_model` per record.
- Designer HyperparamForm: new 3-option selector. Default selected
  = `shaped_v1`; tooltip explains sparse vs learned-shaped trade-off.
- New WS event (optional, Sprint 3) `training:reward_model_metrics`
  carries Φ mean/variance for the dashboard.

## 8. Migration + regression

- **Feature flag** on every new reward path: `sparse_v1` and
  `learned_shaped_v1` code only executes when the field opts in.
- **Default behaviour unchanged** — any caller that doesn't set
  the field keeps `shaped_v1`.
- **Existing tests** (env reward unit tests, parity 22/22, bot
  ladder, league smoke) must stay green — they exercise the
  default path.
- **New tests** required per new reward model: unit tests on the
  formula, golden-log regression on a fixed trajectory, and an
  ablation test confirming farming paths from §1 no longer
  accumulate under `sparse_v1` or `learned_shaped_v1`.

## Open questions

1. Demonstrator diversity: should we mix v1.0.0 vs L1..L5 rollouts
   to avoid Φ overfitting to a single play style? Proposed yes.
2. Φ network size: MLP [64, 64] vs [256, 256]? Default the same as
   the policy backbone for simplicity.
3. Should `shaped_v1` be *retired* after `learned_shaped_v1` reaches
   parity? PM call at end of Sprint 2.

## References

- Ng, Harada, Russell 1999 — potential-based shaping invariance.
- Ziebart 2008 — MaxEnt IRL.
- Fu et al. 2018 — AIRL (`stable-baselines3-contrib` available).
- Christiano et al. 2017 — RLHF preference learning.
- OpenAI InstructGPT 2022 — RLHF pipeline pattern (scripted + human).
