# ADR 0014 — Self-play league (v2.x Sprint 1)

**Status:** proposed
**Date:** 2026-04-18
**Context:** v1.0.0 trains against a fixed `RuleBasedBot` L1-L5 ladder; the
agent's ceiling is the ladder's ceiling. This ADR specifies a PFSP-style
league of past checkpoints (OpenAI Five / AlphaStar pattern) to remove that
ceiling. Code-free design only; implementation plan follows in a later ADR
after stakeholder review.

## 1. Opponent pool

- **Add condition:** every `save_interval` checkpoint (unchanged cadence)
  plus a "league seed" on training start; a checkpoint is admitted only if
  its evaluator rating exceeds the pool minimum by ≥25 Elo (prevents
  regressions from polluting the pool).
- **Size:** fixed cap `LEAGUE_POOL_SIZE = 32` (from AlphaStar's main-pool
  size, fits current GPU VRAM at FP16 policy snapshots).
- **Layout:** new `models/league/{slug}__{exp8}__{step}.zip` directory
  parallel to the existing `models/{experiment_id}/` tree; the manifest
  `models/league/manifest.json` stores `(checkpoint_id, elo, wins, losses,
  games, admitted_at)` tuples.
- **Retirement:** when full, evict the oldest checkpoint whose rating is
  below the pool median ("weakest-and-oldest"); champions never evict.

## 2. Matchmaking

- **Elo init/K-factor:** seed at 1000, K=16 early (< 30 games) → K=8 after
  (standard chess-like annealing). Rule-based baselines pinned at fixed
  anchors (L1=600, L3=900, L5=1200) and never updated.
- **Sampling:** PFSP with `f(x) = (1 − winrate_vs_x)^p`, `p=2` (AlphaStar
  default). Falls back to uniform when fewer than 8 pool entries. Exposed
  as `league.sampling = "uniform" | "elo_proximity" | "pfsp"`; default PFSP.
- **Mirror match:** current learner is NOT in the pool (prevents mode
  collapse); 10% of vec-env slots always play the mirror to keep a
  self-consistency signal.

## 3. Trainer integration

- **Per-env opponent:** extend `PikachuVolleyballEnv.__init__` with
  `opponent_provider: OpponentProvider`. `VecEnv` gets a provider per env
  index; each sub-env pulls a fresh opponent on `reset()` so `n_envs=8`
  sees up to 8 distinct pool members per rollout.
- **Bot class:** new `LoadedPolicyBot` wrapping an SB3 `PPO.load()`
  snapshot; shares `RuleBasedBot.get_action(state, is_player2)` signature
  so existing call sites swap without touching the engine.
- **Inference cost:** +1 policy forward per env-step (CPU-side at batch=1
  is ~0.3 ms on current hardware → <5% wall-clock overhead at n_envs=8).
- **Backward compat:** `bot_level: int | None` still accepted; when set,
  opponent_provider defaults to a `FixedBotProvider(level)`. Deprecation
  warning, not removal.

## 4. League ops

- **Elo update:** per completed match (game, not episode), inside a
  trainer-side callback `LeagueCallback` that drains finished env matches
  from `info["match_result"]`.
- **Persistence:** MongoDB collection `league_standings` (doc per
  checkpoint, indexed on `elo` desc); manifest JSON on disk is the
  authoritative local snapshot, Mongo is the dashboard source.
- **Metrics:** top-N Elo, champion-id history (tracks lineage), per-
  generation mean rating (shows progression), per-checkpoint sample counts.

## 5. L1-L5 coexistence

- **During training:** self-play league only (bot ladder anchors are
  sampled separately at 5% for baseline anchoring).
- **During eval:** keep `evaluator.py` intact — run the trained policy
  against L1..L5 as today for the release-gate scorecard. Adds a new
  league-only eval mode for internal tracking.
- **Mode flag:** `training_mode = "bot_ladder" | "self_play"`; defaults to
  `self_play` in v2.x, fallback to `bot_ladder` if pool is empty at
  training start.

## 6. Difficulty + risk

- **Commits (est.):** BE 6-8 (opponent provider, LoadedPolicyBot,
  LeagueCallback, manifest, Mongo schema, API endpoint, migration), engine
  0 (no physics change), FE 3-4 (league tab, mode toggle, eval split).
- **Parity test (bc2225ea):** not impacted — physics is unchanged; the
  league operates above `env.step()` boundary.
- **Training throughput:** expected -3% to -7% from policy inference
  overhead; acceptable.
- **Novel risks:** (a) pool diversity collapse if all checkpoints come
  from one long run → mitigated by admission Elo gate; (b) PFSP sampling
  bias toward weak opponents if pool stagnates → mitigated by 10% mirror;
  (c) Mongo write amplification on high-frequency matches → batched flush
  per 64 matches.

## 7. FE UX (Designer handoff)

- **Dashboard "League" tab:** table of top 10 by Elo, columns `[rank,
  checkpoint_id, elo, games, win%, admitted_at]`. Champion row
  highlighted. Sortable.
- **Training start modal:** toggle "Opponent: rule-based ladder /
  self-play league"; if league, show current pool size + top Elo.
- **Evaluation page:** two-panel split — "vs L1-L5 ladder" (existing)
  and "vs league top 5" (new). Same scorecard shape.

## 8. Migration + compatibility

- **v1.0.0 checkpoints:** admitted with Elo=1000 (unseeded) via one-shot
  migration script `scripts/seed_league_from_v1_models.py`; marked
  `source="v1_legacy"` in manifest for traceability.
- **WS protocol:** new event `training:league_update` payload
  `{top_n: [...], pool_size, champion_id, generation}` emitted every
  `LEAGUE_BROADCAST_INTERVAL = 64` matches. Existing events unchanged.
- **API:** `GET /api/league/standings?limit=10`,
  `GET /api/league/checkpoint/{id}` (detail + head-to-head), both
  read-only in Sprint 1. Write endpoints deferred to Sprint 2.

## Open questions

1. Champion promotion policy (manual flag vs automatic by Elo +
   consecutive-win streak)? Proposed: automatic, Elo-max held for ≥5
   consecutive admission cycles.
2. Cross-experiment pooling? Proposed NO for Sprint 1 — one pool per
   `experiment_id` to keep ratings comparable; global pool is a Sprint 2
   item.

## References

- OpenAI Five — league via self-play with 80/20 split current/past
- AlphaStar — main/exploiter/league-exploiter pool partition (we use
  "main" only in Sprint 1)
- PFSP — Vinyals et al. 2019 — sampling formula above
- stable-baselines3 — no built-in self-play; SelfPlayWrapper pattern from
  community issue #597 informs the OpponentProvider shape
