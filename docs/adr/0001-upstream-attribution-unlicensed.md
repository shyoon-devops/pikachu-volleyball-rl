# ADR-0001: Upstream attribution — gorisanson/pikachu-volleyball is UNLICENSED

- **Status**: Accepted
- **Date**: 2026-04-13
- **Supersedes**: the prior informal "MIT" claim in commit `1fb72169` and `backend/game/engine.py` docstring
- **Archive**: `docs/reports/notices/NOTICE-ATTRIBUTION-CORRECTION.md`

## Context

The physics port (commit `1fb72169`) originally described the upstream repository `gorisanson/pikachu-volleyball` as MIT-licensed. On re-verification the upstream has (a) no `LICENSE` file, (b) `"license": "UNLICENSED"` in `package.json`, (c) no README claim of MIT or any permissive license. The upstream README additionally characterises the code as reverse-engineered from a 1997 commercial game (Sachi Soft / Sawayakan Programmers), introducing a second-order attribution layer.

## Decision

1. Remove all MIT claims from commit messages and source docstrings; replace with an accurate statement: the upstream is UNLICENSED and the port is a behaviour-compatible re-implementation informed by the original source.
2. `ATTRIBUTION.md` must spell out: upstream repo URL, UNLICENSED status, the acknowledged 1997 commercial origin, and that public release of the port requires separate legal review.
3. Do **not** merge physics-port commits to `dev` until PM signs off on the legal posture.

## Consequences

- Merging the physics port is gated on PM legal sign-off (blocker, not just a paperwork item).
- Any future port from upstream sources inherits the same UNLICENSED posture — documentation must never drift back to "MIT".
- If upstream adds a license later, this ADR is revisited as Superseded; until then, downstream distribution is restricted.
