# ADR-0012: Refactor sprint — area-by-area with strict parity gates

- **Status**: Accepted
- **Date**: 2026-04-19
- **Related commits**: A1 reward decomposition (9 commits ending `7c4a8782`), A2 callbacks decomposition (3 commits ending `068094eb`), A3 test cleanup (`f6f96778`, `bb75db60`), A4 dead code removal (`70ae1162`, `5a0f0aca`, `464f2fa6`, `31b30301`), A5 shared components (`e495b917`, `852598f1`, `cae1f3f4`), A6 WS discriminated union + zod (`de006c0b`, `daf38ad9`), A7 deps bumps (merge `450983df`), A8 ADR migration (merges `7adbc6e3`)

## Context

v0.2.5 landed with substantial hair — reward function had grown into a single 200-line monolithic helper, `LiveFrameCallback` carried three orthogonal responsibilities, FE had dead exports from abandoned experiments, WS messages were dispatched without shape validation, and docs lived in a mix of ad-hoc `NOTICE-*` files with no index.

Before the v1.0 cut we wanted the code **camera-ready** — easy to onboard, easy to reason about, explicitly contract-checked. But we also needed to avoid the classic refactor-regression story where a cleanup PR silently changes runtime behavior.

## Decision

Run a refactor sprint **area by area**, with three strict gates between each area:

### The 8 areas (A1-A8)

| Area | Scope | Owner |
|------|-------|-------|
| A1 | BE `_compute_reward` decomposition into 8 helpers | BE |
| A2 | BE `LiveFrameCallback` 3 helper extraction | BE |
| A3 | BE test coverage cleanup — drop redundant classes superseded by topic-specific files | BE |
| A4 | BE + FE dead code removal (unused flags/exports/helpers/components) | BE + FE |
| A5 | FE shared component extraction (`ScoreCell`, `TimestampText`, `EnvChip`) | FE |
| A6 | FE WS discriminated union + zod runtime validation | FE |
| A7 | deps minor/patch bumps (majors deferred to A7-followup doc) | DevOps |
| A8 | docs ADR migration + `INDEX.md` catalogue | PM |

### The 3 gates between areas

**Gate 1 — Parity**: every area must end with the same outwardly-observable behavior as the area began with. Enforced via:
- Engine parity suite green (inherited from [ADR-0011](0011-faithful-port-with-parity-test.md))
- Full backend test suite green — specifically no relaxed assertions, no `pytest.skip` additions
- FE build + test suites green including visual regression

**Gate 2 — Diff compactness**: each area must fit in **~10 commits or fewer**. If an area needs 20+ commits, it's actually 2+ areas and must be split. A1 at 9 commits and A2 at 3 commits hit this target. A6 at 2 commits was well under.

**Gate 3 — Reviewability**: each commit inside an area must be **individually mergeable**, not require later commits to compile. We used `sed -n '<line1>,<line2>p'` + `python3 -c "import ast; ast.parse(open(f).read())"` locally to verify each commit. The PR #42 trainer syntax incident in v0.2.5 (see [revert `ffe1ae6a`](../../CHANGELOG.md#024---2026-04-12-post-v023-live-ui--engine--hyper-ball-bundle--dev-head-dabd84a1)) is the exact failure mode this gate prevents.

### Commit granularity

Within an area, commits should be **semantic units**, not arbitrary checkpoints:
- A1 each helper extraction was one commit (e.g., `_approach_reward` as `741938f1`, `_score_reward` as `8c5129d8`)
- Final cleanup commit at end removes obsolete locals (e.g., `7c4a8782` drops unused `ball` / `p1` locals)
- Merge commits for each area aggregate the behavior-neutral sequence into one reviewable unit

## Consequences

### Positive

- **Zero regressions across 212 commits.** QA 19/19 PASS at release cut — refactor sprint contributed no new bugs
- **Reviewability is high.** Each area's merge commit shows a clean before/after diff; reviewer doesn't need to trace through intermediate states
- **Future refactors have a template.** A9+ refactors should fit the same mold. The 3 gates are the reusable artifact, not the 8 specific areas

### Negative / costs

- **Lead time is higher than a single "big bang" refactor.** 8 areas × 3 gates ≈ 5 days of elapsed work. A single "rewrite reward.py from scratch" PR would have been ~1 day but risked exactly the kind of silent drift we're guarding against
- **Merge conflicts with active feature branches.** A5 shared component extraction (`ScoreCell`) needed FE branch coordination. We handled it by landing A5 first, then rebasing feature branches onto dev
- **A7 major dep bumps are still open.** Deferred to a separate audit `docs/DEPS-MAJOR-BUMP-CANDIDATES.md`

### Enforcement

- Future refactor sprints must reference this ADR and enumerate their areas + gates before starting
- CI must run the full parity suite (not just unit tests) on any branch prefixed `refactor/` or `v*-prep`
- Single-commit "refactor X" PRs that touch 10+ files are rejected; split into semantic commits

## Alternatives considered

- **"Big bang" single-PR rewrite** — rejected: too risky for pre-major cut; parity test cost is high per run
- **Trunk-based incremental** (land one helper, ship, repeat) — rejected: users were on v0.2.5 runtime during the sprint; we didn't want redeploy churn per-helper
- **Skip the refactor, ship v1.0 as-is** — rejected: maintainability debt would compound and block v1.x feature velocity (self-play league, SAC transition planned)
