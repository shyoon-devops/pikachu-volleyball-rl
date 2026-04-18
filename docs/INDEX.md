# docs/INDEX.md — master catalogue

Entry point for all project documentation. Category owners listed beside each section. If you add a doc, add a line here.

## Architecture Decision Records (`adr/`)

Short, durable records — **one decision per file**. ADRs can be `Accepted`, `Superseded`, or `Deprecated`.

| # | Title | Status |
|---|-------|--------|
| [0001](adr/0001-upstream-attribution-unlicensed.md) | Upstream attribution — gorisanson/pikachu-volleyball is UNLICENSED | Accepted |
| [0002](adr/0002-fe-keyboard-input-contract.md) | Frontend keyboard input contract (original-faithful) | Accepted |
| [0003](adr/0003-rl-reward-rebalance.md) | RL reward rebalance — terminal-dominant shaping | Accepted |
| [0004](adr/0004-bot-ladder-ordering-deferred.md) | Bot-ladder ordering regression (L3>L4, L2>L4) — deferred | Accepted (defer-until-post-v1) |
| [0005](adr/0005-post-merge-health-check-mandatory.md) | Post-merge health check is mandatory for the merging author | Accepted |
| [0006](adr/0006-fx-payload-engine-fields-contract.md) | Engine FX and freeze-frame fields — WS payload contract | Accepted |
| [0007](adr/0007-canvas-pixel-art-rendering.md) | Canvas pixel-art rendering — NEAREST + roundPixels | Accepted |
| [0008](adr/0008-ws-gameresult-payload-validation.md) | Validate `game:result` WS payloads against the full `GameRecord` schema | Accepted |
| [0009](adr/0009-fe-dual-channel-dispatch-and-hydration.md) | FE dispatches commands on both WS + REST, and hydrates state on mount / reconnect | Accepted |
| [0010](adr/0010-devops-redeploy-batching.md) | DevOps batches in-flight merges into the current redeploy cycle | Accepted |

Next ADR number: **0011**.

## Design specs (`design/`)

Living UX / frontend specs. Each file is self-contained and may supersede earlier ones — check for `SUPERSEDED BY` banners at the top.

- [DESIGN-BATCH-TABS.md](design/DESIGN-BATCH-TABS.md) — parallel env viewer tabs under `GameCanvas`
- [DESIGN-HYPERPARAM-FORM.md](design/DESIGN-HYPERPARAM-FORM.md) — expanded PPO hyperparameter form
- [DESIGN-TRAINING-TITLE.md](design/DESIGN-TRAINING-TITLE.md) — training-run title field + propagation
- [DESIGN-HISTORY-DRILLDOWN.md](design/DESIGN-HISTORY-DRILLDOWN.md) — *SUPERSEDED by* [DESIGN-RUNS-MERGED.md](design/DESIGN-RUNS-MERGED.md)
- [DESIGN-EVAL-DRILLDOWN.md](design/DESIGN-EVAL-DRILLDOWN.md) — *SUPERSEDED by* [DESIGN-RUNS-MERGED.md](design/DESIGN-RUNS-MERGED.md)
- [DESIGN-BULK-DELETE.md](design/DESIGN-BULK-DELETE.md) — multi-select checkpoint deletion UX
- [DESIGN-RUNS-MERGED.md](design/DESIGN-RUNS-MERGED.md) — unified Training Runs nav + sub-tabs (current)

## Audits (`audits/`)

Code-vs-upstream cross-walks. Updated during / after every parity sweep.

- [AUDIT-ORIGINAL-CONSTANTS.md](audits/AUDIT-ORIGINAL-CONSTANTS.md) — authoritative inventory of upstream physics constants
- [AUDIT-PORT-DIFF.md](audits/AUDIT-PORT-DIFF.md) — port diff vs original (per-constant status)
- [AUDIT-STATE-MACHINE-DIFF.md](audits/AUDIT-STATE-MACHINE-DIFF.md) — controller and player state-machine cross-walk

## Asset inventories (`assets/`)

- [ORIGINAL-INVENTORY.md](assets/ORIGINAL-INVENTORY.md)
- [CURRENT-DIFF.md](assets/CURRENT-DIFF.md)
- [PORT-CHECKLIST.md](assets/PORT-CHECKLIST.md)

## Reports archive (`reports/`)

Historical PM/team reports and diagnostic write-ups. Treat as read-only history.

- [REPORT-BOT-DIFFICULTY-UPGRADE.md](reports/REPORT-BOT-DIFFICULTY-UPGRADE.md) — 2026-04-12 (see ADR-0004)
- [REPORT-PM-20260412.md](reports/REPORT-PM-20260412.md)
- [REPORT-PM-20260412-P0-MATCHEND.md](reports/REPORT-PM-20260412-P0-MATCHEND.md) — (see ADR-0010)
- [REPORT-PM-20260412-MERGE-COMPLETE.md](reports/REPORT-PM-20260412-MERGE-COMPLETE.md) — (see ADR-0010)
- [REPORT-PM-20260413-PHYSICS-PORT.md](reports/REPORT-PM-20260413-PHYSICS-PORT.md) — (see ADR-0001)
- [REPORT-POWER-HIT-DIAGNOSTIC.md](reports/REPORT-POWER-HIT-DIAGNOSTIC.md) — (see ADR-0006)

### Original notices (`reports/notices/`)

Full-length NOTICE dispatches, kept for context behind each ADR. Every ADR names the notice it summarises.

## Incidents (`incidents/`)

Post-mortems and runbooks for real incidents.

- [20260412-dev-backend-stale.md](incidents/20260412-dev-backend-stale.md) — (see ADR-0005)

## Releases (`releases/`)

Per-version release notes. See the `releases/` directory; TEMPLATE.md lists the required sections.

## Operational docs (root of `docs/`)

- [PLAN.md](PLAN.md) — current roadmap
- [WORKFLOW.md](WORKFLOW.md) — team process + merge / health-check rules (reflects ADR-0005)
- [DEPLOYMENT-STATUS.md](DEPLOYMENT-STATUS.md) — live deployment state
- [DELIVERABLES-CHECKLIST.md](DELIVERABLES-CHECKLIST.md)
- [EVAL_CRITERIA.md](EVAL_CRITERIA.md), [METRICS.md](METRICS.md), [ENV_SPEC.md](ENV_SPEC.md)
- [SCOPE-BOUNDARIES.md](SCOPE-BOUNDARIES.md)
- [SPRINT1-ASSIGNMENT.md](SPRINT1-ASSIGNMENT.md), [SPRINT2-STATUS.md](SPRINT2-STATUS.md)
- [DISK-CLEANUP-REPORT-20260412.md](DISK-CLEANUP-REPORT-20260412.md)
- [VERSIONS.yml](VERSIONS.yml) — version matrix

## How to add a new ADR

1. Copy an existing ADR as a template; bump the number to `NNNN`.
2. Fill in `Status` (usually `Accepted`), `Date`, optional `Supersedes` / `Archive` links.
3. Write `Context → Decision → Consequences`. One decision per file.
4. Add the row to the ADR table above.
5. If it supersedes an older ADR, mark the older one `Status: Superseded by ADR-NNNN` at the top.
