# ADR-0011: Faithful port with parity test as acceptance criterion

- **Status**: Accepted
- **Date**: 2026-04-19
- **Supersedes**: prior ad-hoc "close-enough" port gates in v0.2.x
- **Related commits**: `1fb72169` (physics.js port), `d8dc8bb6` (view.js port), `8add0ea6` (golden 10-scenario tests), `bc2225ea` (frame-by-frame parity), `68f18b85` (constants audit), `d8f775f7` (port-vs-original diff), `c3912faa` (state-machine cross-walk)

## Context

Through v0.2.x we kept running into **subtle physics divergences** from the upstream 1997 `gorisanson/pikachu-volleyball` source — ball bounces feeling too floaty, bot reaction timings drifting, match-end freeze tick order wrong, sky gradient dropping RGB stripes, slo-mo transition missing, etc. Each incident had the same failure mode:

1. Our port had been done "by feel" in an earlier pass and passed light unit tests
2. A specific user report surfaced one cell of divergence
3. We patched that cell in isolation, which sometimes broke an adjacent cell
4. Weeks later another cell's divergence surfaced

The v0.2.5 P0 match-end freeze (`cd1e6a39`) was the latest instance. It was diagnosed as a 1-line tick-ordering bug in the engine, but the reason we never caught it earlier was that **we had no frame-accurate parity harness against the upstream source**.

## Decision

For the v1.x major cut, adopt **faithful port with parity test as acceptance criterion** as the standard for any code that ports an upstream system:

1. **The upstream source is authoritative.** Constants, branch order, tick cadence, sprite indexing — our port must match cell-for-cell unless we have a written deviation justification in this repo
2. **Port is not complete until the parity test exists.** Before merging a port PR:
   - 10+ scenario golden test must pass byte-wise against a captured upstream snapshot
   - Frame-by-frame parity suite must pass for at least 60 seconds (3600 frames @ 60fps or equivalent) against upstream reference trace
   - Determinism regression test must be in place (same seed → same trace)
3. **Audit documents are first-class deliverables.** Every port must ship:
   - Constants inventory (`docs/audits/AUDIT-ORIGINAL-CONSTANTS.md` pattern) — every named constant with upstream file:line
   - Port-vs-original diff (`AUDIT-PORT-DIFF.md`) — each ported cell marked MATCH / INTENTIONAL-DIFF / NOT-PORTED
   - State-machine cross-walk (`AUDIT-STATE-MACHINE-DIFF.md`) — every state with its ported / extended / dropped status
4. **Intentional deviations require a recorded reason.** A port cell may diverge from upstream only with a one-line justification in the audit docs. "We made it better" without evidence is not sufficient.

Physics port `1fb72169` + view port `d8dc8bb6` + golden tests `8add0ea6` + 11k frame-parity assertions `bc2225ea` + 3 audits `68f18b85` / `d8f775f7` / `c3912faa` is the **reference implementation** of this policy.

## Consequences

### Positive

- **Silent divergence is impossible.** Any future edit to engine.py that introduces drift fails the parity suite at CI, not at user smoke
- **Downstream fixes are surgical.** Once parity is the floor, a new bug report immediately localizes to the single cell that disagrees with upstream
- **Port work is auditable.** Reviewers can compare the 3 audit files against a single upstream ref and sign off mechanically rather than inspecting 30k LOC by hand

### Negative / costs

- **Port effort is higher up front.** Adding parity tests roughly doubled the physics port landing cost vs. the old "close-enough" approach
- **Reference traces must be captured + committed.** Binary golden snapshots increase repo size (mitigated: msgpack, not raw frames)
- **Upstream divergence cost**: if upstream changes, our parity fails — we must decide whether to follow or pin. Policy: pin by default, follow with a fresh audit commit

### Enforcement

- Port PRs without the 3 audit docs + golden tests are blocked at review
- Non-port PRs that touch ported files must show passing parity suite in CI summary
- Drift detected in production → treat as P0 regression against the parity contract

## Alternatives considered

- **"Fix-forward and retest"** (status quo through v0.2.x) — rejected: we've shown this pattern leaks for weeks before surfacing
- **Port only the spec, not the code** (clean-room reimpl from design doc) — rejected: too much tribal knowledge in the upstream code (tick order, sprite base frame index, off-by-one frame counters) to recover from a spec
- **Full machine-translation of upstream JS** — rejected: binds us to upstream runtime assumptions (DOM/canvas timing) that don't hold in our headless Gymnasium env
