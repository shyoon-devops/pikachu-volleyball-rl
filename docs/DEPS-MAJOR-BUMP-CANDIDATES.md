# Major Dependency Bump Candidates

Tracking deps that were flagged during A7 audit but deliberately skipped in this
sprint because they are major bumps, cross large 0.x gaps that pre-1.0 projects
treat as effectively breaking, or are pinned by a peer library. Each entry needs
its own sprint with migration notes before we adopt.

Audit baseline: `v1.x-prep @ 3b3b626c` (2026-04-18).

---

## Frontend (`frontend/package.json`)

### `@eslint/js` 9.39.4 → 10.0.1 (MAJOR)

- Flat-config only. We already ship `eslint.config.js`, but a few legacy rule
  names and plugin entry points moved.
- Coupled with `eslint` 9 → 10 — bump both in one change, not individually.
- Ref: https://eslint.org/blog/2026/01/eslint-v10.0.0-released/

### `eslint` 9.39.4 → 10.2.1 (MAJOR)

- Paired with `@eslint/js` 10. Verify `typescript-eslint` 8.x runs on 10 (support
  confirmed on 8.58+, which we already have — low risk, still a major).

### `@types/node` 24.12.2 → 25.6.0 (MAJOR)

- Type-only; does not change runtime. Safe to bump when we also drop Node 22
  CI coverage. Defer until we settle the Node runtime matrix.

---

## Backend (`backend/pyproject.toml`)

### `fastapi` 0.115.0 → 0.136.0 (21 minor releases, treat as breaking)

- Pre-1.0. Small per-release deltas, but 21 versions span lifespan changes,
  header-helper deprecations, and a revised dependency-override API that we
  use in `conftest.py`. Needs an integration-test sweep.
- Start by bumping to 0.120 (known-good with current Pydantic / starlette
  combo) and iterating, not a single hop.

### `uvicorn[standard]` 0.30.6 → 0.44.0 (14 minor releases, treat as breaking)

- Pre-1.0. Logging config shape changed around 0.34. Several projects have hit
  WebSocket lifespan regressions on 0.4x. Verify `/ws` path end-to-end before
  adopting.

### `pytest` 8.3.3 → 9.0.3 (MAJOR — CVE-2025-71176)

- Security: CVE-2025-71176 fixed in 9.0.3 (vuln noted in `pip-audit`).
- Breaking: removed legacy `pytest.ini` options, asyncio plugin contract, and
  several deprecated hooks. `pytest-asyncio 1.3` is compatible with 9, but
  needs a dry run on our parity harness + e2e suite.
- This is the highest-priority skipped bump because it is the only direct-dep
  CVE flagged by `pip-audit` against our project requirements.

---

## Not Actionable This Sprint

### Backend has no lockfile

`backend/pyproject.toml` uses `>=` floors only. Without a `requirements.lock`
/ `uv.lock` / `poetry.lock`, "bumping" a transitive dep has no file to commit.
Installed versions resolve at Docker build time. If we want deterministic
builds, adding a lockfile is a prerequisite and is out of scope for A7.

### System-wide CVEs

`pip-audit` reports 53 vulnerabilities across 20 packages in the host Python
environment (certifi, cryptography, idna, jinja2, pillow, pip, pyopenssl,
etc.). None are direct project deps — they belong to the WSL/Ubuntu system
Python and should be patched via the OS package manager, not by us.

---

## Summary

| Area     | Skipped           | Reason                              |
|----------|-------------------|-------------------------------------|
| Frontend | `@eslint/js` 10   | major (flat-config deltas)          |
| Frontend | `eslint` 10       | major (paired with @eslint/js 10)   |
| Frontend | `@types/node` 25  | major (Node runtime matrix pending) |
| Backend  | `fastapi` 0.136   | 21 minor hops on a pre-1.0 lib      |
| Backend  | `uvicorn` 0.44    | 14 minor hops on a pre-1.0 lib      |
| Backend  | `pytest` 9        | major + CVE-2025-71176 fix          |
