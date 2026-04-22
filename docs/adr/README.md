# Architecture Decision Records

Short, durable records — **one decision per file**. Each ADR is `Accepted`, `Superseded`, or `Deprecated`. The numbering is monotonic across the project lifetime; retiring an ADR uses a `Status: Superseded by NNNN` header rather than removing the file.

The full project documentation catalogue is [`docs/INDEX.md`](../INDEX.md); this README is the local index for the ADR directory specifically.

## Index

| # | Title | Status |
|---|-------|--------|
| [0001](0001-upstream-attribution-unlicensed.md) | Upstream attribution — gorisanson/pikachu-volleyball is UNLICENSED | Accepted |
| [0002](0002-fe-keyboard-input-contract.md) | Frontend keyboard input contract (original-faithful) | Accepted |
| [0003](0003-rl-reward-rebalance.md) | RL reward rebalance — terminal-dominant shaping | Accepted (see 0015 for v2 evolution) |
| [0004](0004-bot-ladder-ordering-deferred.md) | Bot-ladder ordering regression (L3>L4, L2>L4) — deferred | Accepted (defer-until-post-v1) |
| [0005](0005-post-merge-health-check-mandatory.md) | Post-merge health check is mandatory for the merging author | Accepted |
| [0006](0006-fx-payload-engine-fields-contract.md) | Engine FX and freeze-frame fields — WS payload contract | Accepted |
| [0007](0007-canvas-pixel-art-rendering.md) | Canvas pixel-art rendering — NEAREST + roundPixels | Accepted |
| [0008](0008-ws-gameresult-payload-validation.md) | Validate `game:result` WS payloads against the full `GameRecord` schema | Accepted |
| [0009](0009-fe-dual-channel-dispatch-and-hydration.md) | FE dispatches commands on both WS + REST, and hydrates state on mount / reconnect | Accepted |
| [0010](0010-devops-redeploy-batching.md) | DevOps batches in-flight merges into the current redeploy cycle | Accepted |
| [0011](0011-faithful-port-with-parity-test.md) | Faithful port with parity test as acceptance criterion | Accepted |
| [0012](0012-refactor-sprint-area-by-area-with-parity-gates.md) | Refactor sprint — area-by-area with strict parity gates | Accepted |
| [0013](0013-unified-runs-navigation.md) | Unified Training Runs navigation replacing /history + /evaluation split | Accepted |
| [0014](0014-self-play-league.md) | Self-play League (v2.x Sprint 1) | Accepted |
| [0015](0015-reward-simplification.md) | Reward simplification (v2.x Sprint 2) | Accepted |
| [0016](0016-lstm-recurrent-policy.md) | LSTM recurrent policy (v2.x Sprint 3) | Accepted |
| [0017](0017-sac-continuous-actor-critic.md) | SAC actor-critic (v2.x Sprint 4) | Accepted |
| [0018](0018-dreamer-v3-world-model.md) | Dreamer V3 world-model (v2.x Sprint 5) | Accepted (Experimental) |

**Next ADR number:** `0019`.

## Organization by release

- **v0.2 foundations**: 0001-0010 — attribution, input contract, reward v1, bot ladder, health checks, FX/WS contracts, canvas rendering, redeploy batching
- **v1.0 major**: 0011-0013 — parity port methodology, refactor-sprint gates, unified /runs navigation
- **v2.0 major**: 0014-0018 — algorithm matrix (self-play, reward, policy, algorithm, world-model)
- **v3.0+**: next ADRs for self-play league scaling, mixed-algorithm Elo, league-based curriculum

## How to add an ADR

1. Copy an existing ADR as a template — 0013 is a good shape for a user-facing architectural change, 0011 for a methodology.
2. Use the next available number. Update the table above and `docs/INDEX.md`.
3. Set `Status: Accepted` only after a decision is final. Use `Proposed` for design-in-progress drafts; they don't count against the `Next ADR number` until promoted.
4. Link to related commits by SHA, to related ADRs by number, to related design specs by path.
5. The file is the contract. Don't rewrite an accepted ADR; add a new one with `Supersedes: NNNN` in the header and update the table here with `Superseded by MMMM`.

## References

- [docs/INDEX.md](../INDEX.md) — full project documentation catalogue
- [docs/design/](../design/) — living UX / frontend specs
