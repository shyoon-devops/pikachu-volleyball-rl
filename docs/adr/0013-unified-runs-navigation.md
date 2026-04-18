# ADR-0013: Unified Training Runs navigation replacing /history + /evaluation split

- **Status**: Accepted
- **Date**: 2026-04-19
- **Design spec**: [`docs/design/DESIGN-RUNS-MERGED.md`](../design/DESIGN-RUNS-MERGED.md)
- **Related commits**: `1c4779cd` (unified Training Runs with sub-tabs), `dd747d76` (hyperparams on run detail), `ef12e751` (history 2-level drill-down), `385bfc1d` (eval 2-level drill-down), `31b30301` (TrainingRunDetail deletion), `06273e04` (10 hyperparam fields mapping)

## Context

Through v0.2.x the dashboard exposed three separate user flows:

1. **`/history`** — flat list of every game, no grouping
2. **`/evaluation`** — flat list of every evaluation run, no grouping
3. **Training Run Detail** — a third page shown only transiently during live training

The three flows didn't talk to each other. A user who wanted "what did my `pika-l5-test-3` run look like?" had to:
1. Find the start timestamp (from memory / WS log)
2. Go to `/history`, filter by that time range, see the games
3. Remember the experiment_id from the games
4. Go to `/evaluation`, filter by experiment_id, see the checkpoints
5. Mentally correlate the two lists

Multiple user reports in rounds 6-9 pointed at this friction. The worst was R9 (`22e1fe55`) where the evaluation results tab just didn't show anything for the current run — because the run-level linking didn't exist server-side either.

## Decision

Unify all three surfaces into **`/runs`** — a single screen keyed by training run, with sub-tabs for Overview / Games / Evaluation. Tear down the split.

### Information architecture

**Top level** — list of training runs:
- Filterable by title (R6 `T4` aggregation)
- Shows run-level summary: title, started_at, total games, latest eval verdict
- Powered by `GET /api/training/runs` aggregation (BE-T4, hyperparams merged in via BE-T10)

**Run detail** — opens a run with 3 sub-tabs:
- **Overview**: hyperparams (10 fields), run lifecycle, metrics chart
- **Games**: games list filtered to this run (via `title` match, BE-T5). Supports live prepend via `training:game_end` WS event (BE-T7, `f506a887`)
- **Evaluation**: evaluation results filtered to this run (via `experiment_id` match, BE-T11)

### Supporting backend changes

- `GameRecord.title` + `.experiment_id` + `.current_episode` fields (BE-T1, T5, T6)
- `EvaluationRecord.title` + `.experiment_id` (BE-T11)
- `training:game_end` WS event (BE-T7) for live Games sub-tab
- `/api/training/runs` aggregation returning 10 hyperparams (BE-T10)
- Legacy backfill: `/api/evaluation/results` injects `title` on read (BE-T12)

### Supporting frontend changes

- Sub-tab navigation synced to URL (`?tab=overview|games|evaluation`)
- `UnifiedRunDetail` component replaces transient `TrainingRunDetail` (deleted in A4 dead-code cleanup, `31b30301`)
- 2-level drill-down: top list of runs → run detail → within detail, games/evaluation lists
- `training:game_end` WS subscriber prepends to FE history cache (flicker-free keys + memo, R7 `e64604f5`)
- Stable component reuse via shared `ScoreCell` / `TimestampText` / `EnvChip` (A5)

## Consequences

### Positive

- **One mental model for a user: "give me run X"** — no more multi-page correlation dance
- **URLs are shareable.** `/runs/<title>?tab=evaluation` is a deep-link into the exact view
- **Title is the join key everywhere.** Previous incidents where evaluation couldn't find its run (R9) become structurally impossible: same title, same server-side filter
- **Live update is natural.** `training:game_end` prepends directly into the sub-tab the user is looking at
- **Future features compose.** Self-play league tracking (planned for v1.x+) maps cleanly onto "multiple checkpoints of the same title played against each other" — the unified view already has the join key

### Negative / costs

- **Breaking change** for external bookmarks to `/history` or `/evaluation`. v1.0.0 release notes flag this; redirects are a v1.0.1 candidate
- **Backfill complexity.** Legacy MongoDB docs don't have `title` or `experiment_id`. Solved via dual path (read-side inject T12 + write-side propagation T1..T6 + one-shot migrate script). But users running raw MongoDB queries must update
- **URL query-param inconsistency.** `?tab=evaluation` vs `?tab=eval` depending on entry point — flagged as known issue for v1.0.1 hotfix
- **Sub-tab performance.** Each sub-tab fetches its slice independently. Acceptable at current scale but may need prefetch when runs grow to 100+ games

### Enforcement

- Future views that touch "game data" or "evaluation data" must route through `/runs`. Adding a flat top-level `/games` or `/evaluations` requires overturning this ADR
- `GameRecord` and `EvaluationRecord` schema evolution must preserve the title-as-join-key invariant
- Any new run-level field added to BE (e.g., future `league_id`, `seed_recipe`) must be exposed on the run detail Overview sub-tab, not a new top-level page

## Alternatives considered

- **Keep the split, add cross-links** — rejected: still forces the user to follow 2-3 clicks to reach the correlated view, and the backend doesn't actually guarantee the data is consistent across filters
- **Replace with a single flat list sorted by time** — rejected: loses run-level grouping, makes "what was my best run?" queries harder, doesn't scale past ~hundreds of entries
- **Per-run dedicated pages (`/runs/:title`) without a top list** — rejected: requires knowing the title up-front; no way to explore unknown runs. The top list is the entry point
- **Defer to v1.1** — rejected: the R9 "evaluation tab shows nothing" bug was surfaced by users as CRITICAL for v1.0, and fixing it properly meant building the unified join key
