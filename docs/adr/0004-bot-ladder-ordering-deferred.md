# ADR-0004: Bot-ladder ordering regression (L3>L4, L2>L4) — deferred

- **Status**: Accepted (defer-until-post-v1)
- **Date**: 2026-04-13
- **Priority**: P2 (tuning quality, not correctness)
- **Archive**: `docs/reports/notices/NOTICE-BOT-LADDER-FOLLOWUP.md`
- **Related**: `REPORT-BOT-DIFFICULTY-UPGRADE.md`, ADR-0003 (reward rebalance)

## Context

After the physics port and L5 regression fix, full L1-vs-L1..L5 ladder measurement (15-game batches, 4 seed bases) revealed two stable inversions: **L3 beats L4** (2/15 for the higher level) and **L2 beats L4** (5/15). L1→L2, L4→L5, L1→L5 ordering is correct. Root cause is structural, not noise: the ported physics rewards late-commit aggression (10-frame state=2 power-hit dwell window) and punishes early-commit intercepts. Precise high-level bots position for exact alignment and lose on `vx=0` rand() tiebreaks; noisier mid-level bots land inside the dwell window and power-hit reliably.

## Decision

Defer retuning of BOT_PARAMS levels 2–4 until after v1 ships. Rationale: (a) the inversion is within difficulty *tuning*, not correctness — bots still play, the order just isn't monotonic in the L2/L3/L4 range; (b) retuning requires a multi-seed sweep that will churn alongside the ADR-0003 fresh-training work; (c) the user-facing difficulty selector still offers 5 distinguishable bots.

When we do revisit, the handles to adjust (in order of expected impact) are: (1) widen L3/L4 `jump_timing_error` delta, (2) sharpen L4 `powerhit_probability` above L3, (3) consider reducing the `state=2` dwell as a global parity deviation (separate ADR if taken).

## Consequences

- Difficulty ladder docs should note "L2/L3/L4 are within a skill band; L1, L5 are the reliable anchors" rather than claiming strict monotonicity.
- Any eval harness that assumes monotonic win-rate progression across L1..L5 will need a band tolerance; don't auto-flag L3>L4 as a regression.
- Revisiting this ADR requires re-measuring against the current physics parity baseline (ADR-0003 may have shifted the table).
