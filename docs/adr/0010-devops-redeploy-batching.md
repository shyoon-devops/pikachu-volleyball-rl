# ADR-0010: DevOps batches in-flight merges into the current redeploy cycle

- **Status**: Accepted
- **Date**: 2026-04-12
- **Archives**: `docs/reports/notices/NOTICE-DEVOPS-20260412-MERGE.md`, `docs/reports/notices/NOTICE-DEVOPS-20260412-P0-MERGE.md`

## Context

Two coordination incidents on the same day: a P0 match-end freeze fix (`e9f72459 + cd1e6a39`) and a sky-stripe fix + FE/BE notices merge (`a0dafa30` pulling in `fb197f89`, `ff24cc9a`, `a8582e1a`) both landed while DevOps was mid-cycle on a redeploy. Merging authors had to explicitly flag each push and ask DevOps to include it in the in-flight build. Without the flag the commits would have landed on the next cycle — minutes to hours of avoidable user-facing breakage.

## Decision

Adopt a **last-merge-wins** batching policy for DevOps redeploy cycles:

1. When DevOps starts a cycle, they snapshot the current `dev` tip and call out the SHA in the team channel.
2. Any author pushing to `dev` **during** the cycle is responsible for notifying DevOps with the new tip SHA + what the merge contains (touched paths, build impact).
3. DevOps rebases the build onto the latest `dev` tip at build time (not at cycle-start-time), so in-flight pushes are picked up.
4. Authors provide a one-line impact tag: `FE-only` / `BE-only` / `docs-only` / `both`, so DevOps knows whether to rebuild one or both container images.

The P0 freeze fix (match-over guard reorder in `engine.step()`) is the reference example: ~15-line diff, BE-only, engine tests 30/30, backend suite 379 passed — batched successfully into the in-flight cycle.

## Consequences

- DevOps never freezes `dev` during a build; authors still have a responsibility window where they must coordinate.
- If the cycle timing is short (< 5 min), authors should wait rather than interrupt.
- Build-time rebase means reproducibility depends on a known `dev` SHA — DevOps must record the actual rebuilt tip in their release notes (`docs/releases/vX.Y.Z.md`), not the cycle-start SHA.
- Docs-only merges don't require rebuild; the one-line tag avoids unnecessary cycles.
