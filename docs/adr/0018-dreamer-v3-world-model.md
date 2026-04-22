# ADR 0018 — Dreamer V3 world-model (v2.x Sprint 5, final)

**Status:** proposed · **Date:** 2026-04-22

**Context:** S1 self-play + S2 reward_model + S3 LSTM + S4 SAC on
dev. Roadmap priority #5 — the **last** v2.x sprint — introduces a
model-based learner so sample-efficiency steps past what on-policy
PPO + off-policy SAC can hit with model-free replay alone. Code-
free per PM.

## 1. Motivation

PPO plateaus near 0.62 L3-winrate at ~1.5M steps (ADR 0016 §1);
SAC (ADR 0017) targets a 30% sample-efficiency cut but still
learns from raw transitions. Dreamer V3 fits a **world model** to
the same transitions and trains actor/critic inside imagined
rollouts — each real env step amortises over dozens of virtual
ones. Pika Volleyball fits unusually well: physics is
**deterministic** (no env stochasticity to smear the latent),
rallies are **short-horizon** (~150-frame median) so the RSSM
prior doesn't need long-range credit, and the 18-float obs keeps
the encoder / decoder cheap without CNN features.

## 2. Dreamer V3 overview

Hafner et al. 2023. Three networks jointly trained:
**World model (RSSM)** — encoder `o → e`, recurrent GRU over
`(e, a, h_{t-1})`, posterior `z ~ q(z|h,e)`, prior `ẑ ~ p(ẑ|h)`,
decoder reconstructs obs+reward+continue from `(h, z)`.
**Actor** `π(a|h,z)` — trained in **imagination** on prior-rolled
sequences only (no real env during AC update). **Critic** `V(h,z)`
with target network + λ-return bootstrap. Atari100k + DMC
benchmarks show ~5× step savings vs PPO at matched compute; we
budget **2M real env steps** to reach PPO shaped_v1's 10M-step
baseline (§9).

## 3. Action space fit

Env stays `Discrete(12)` (ADR 0017 §2). Dreamer V3 ships a
discrete actor head (categorical over |A| with straight-through
gradient on the sampled one-hot); no continuous re-mapping.
ACTION_MAP, `LoadedPolicyBot` mirror, replay msgpack, S3/S4
checkpoints all untouched.

## 4. Boundary contract

Extends the ADR 0017 `algorithm` enum — no new field. Mirrors the
S2-S4 pattern: enum `algorithm: 'ppo' | 'sac' | 'dreamer_v3'`,
default `'ppo'`; `WsTrainingStartPayload.algorithm` Literal
extended, unknown → Pydantic `payload_invalid`; `/api/training/runs`
+ `/runs/{title}` surface `dreamer_v3` on new rows, legacy keep
`'ppo'`. **No new migration** — the S4 backfill already covered
the field. `policy_type` is **orthogonal and ignored** when
`algorithm='dreamer_v3'`: Dreamer's RSSM replaces MLP/LSTM as the
temporal feature extractor, so the distinction has no runtime
meaning. The record still persists the caller's `policy_type` for
audit consistency, matching how reserved policy_types were handled
in ADR 0016.

## 5. Library choice

- **A — `dreamerv3`** (Hafner official PyPI v1.5.0): TF/JAX. Adds
  a second DL framework (+~1.4 GB image), two checkpoint formats
  for `LoadedPolicyBot` to learn.
- **B — `dreamerv3-torch`** (NM512, GitHub only): PyTorch port,
  stack-aligned. Cost: no PyPI release → pin by git+SHA in
  pyproject (supply-chain exposure on upstream force-push).
- **C — Vendor**: ~1500-2000 LOC; prohibitive vs S4's 450 LOC SAC
  vendor.

**Recommendation: B.** Single framework matches existing SB3 +
sb3-contrib + vendored SAC-Discrete PyTorch stack —
`LoadedPolicyBot`, checkpoint plumbing, GPU kernels compile once
at image build. Supply-chain risk mitigated by pinning a specific
commit SHA (not `main`) and vendoring a lockfile.

## 6. Training loop differences

SB3's `model.learn(total_timesteps)` is a single collect-rollout +
train call. Dreamer's loop runs three phases per iteration:
(1) env interaction — N steps into a replay buffer (layout shared
with SAC's, so `_n_updates` + checkpoint cadence reuse);
(2) world-model train — sample trajectories, fit encoder / RSSM /
decoder on reconstruction + KL; (3) AC train — roll imagined
sequences from the posterior through the learned prior, update
actor + critic on latent λ-returns. `trainer.py` branches on
`self._algorithm == 'dreamer_v3'`, bypassing `model.learn` for a
dedicated `backend/rl/dreamer_train_loop.py`. The
`_StopEventCallback` / `MetricsCallback` / `UpdateWindowCallback`
hooks fire on the env-interaction step boundary so the WS overlay
stays accurate — Fix A (ADR 0014) semantics preserved.

## 7. Hyperparameter pinning

ADR 0016 pattern — no WS surfacing, no override exposed in v2.x.
`DREAMER_DEFAULT_KWARGS`: `rssm_hidden_size=512`, `latent_dim=32`
(discrete 32×32 categorical latent, Hafner 2023 default);
`world_model_lr=1e-4`, `actor_lr=3e-5`, `critic_lr=3e-5`;
`imagine_horizon=15`, `batch_size=16`, `sequence_length=64`;
`replay_capacity=1_000_000`, `train_every=16` (env steps per
gradient step). Advanced knobs (KL-balance, free-bits, entropy
schedule) stay at paper defaults — a tuning surface would blow
past S5's final-sprint budget and undercut the experimental FE
badge's promise.

## 8. UI impact

Extends the S4 `HyperparamForm.algorithm` selector with a third
option `'Dreamer V3'`. **Experimental** badge identical to
`learned_shaped_v1` in the reward selector (S2 pattern). Chip
label `"DreamerV3"` on the runs table. `HyperparamsSummary` gains
no new row — reuses the algorithm row. Designer UX spec not
required; S4 selector surface carries over.

## 9. Success criteria

Matched-compute on `bot_ladder L3` + `shaped_v1`:
**sample-efficiency (primary)** Dreamer V3 reaches PPO's 10M-step
`winrate_vs_L3` in ≤ **2M** real env steps (5× saving, 20% of
PPO's budget); **final-quality** at 10M steps, `winrate_vs_L3` ≥
PPO on matched hardware; **wall-clock** ≤ **3×** PPO on the 4070 Ti
— the world-model train pass adds significant GPU time per env
step, 3× is the ceiling where researcher iteration stays tolerable.
Miss two → Dreamer stays **experimental opt-in**; default `ppo`.
Eval scorecard reuses S3/S4 columns; a Dreamer-specific
`world_model_kl` row on the training dashboard surfaces RSSM
collapse during debugging.

## 10. Migration + feature flag

No new Mongo migration — S4's `algorithm` backfill already stamped
legacy docs `'ppo'`; adding `'dreamer_v3'` touches the Literal
membership at the schema layer only. `policy_type` persists on the
run record even for Dreamer runs (audit trail, not runtime
dispatch) and the trainer explicitly ignores it when
`algorithm='dreamer_v3'`. Checkpoints stay `{slug}__{exp8}__final.zip`
but internals are a torch state-dict of RSSM + actor + critic +
replay — **NOT cross-loadable** with PPO / SAC, same contract as
ADR 0017 §9. Feature flag IS the enum value; no separate toggle.
On the FE, an experimental badge + first-time confirm-dialog steer
non-experienced users back to PPO.

**Open:** (1) whether to surface `imagine_horizon` override on WS
once initial runs land — proposed defer to v3.x; (2) pinning
`dreamerv3-torch` by SHA vs tag — proposed SHA (tags on that repo
are not signed). **Refs:** Hafner et al. 2023 "Mastering Diverse
Domains through World Models" (Dreamer V3 paper); NM512/dreamerv3-
torch (chosen PyTorch port); SB3 OffPolicyAlgorithm (replay buffer
compat with §7).
