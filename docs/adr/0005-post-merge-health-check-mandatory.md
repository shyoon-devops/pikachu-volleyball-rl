# ADR-0005: Post-merge health check is mandatory for the merging author

- **Status**: Accepted
- **Date**: 2026-04-12
- **Archive**: `docs/reports/notices/NOTICE-HEALTH-CHECK.md`
- **Reflected in**: `docs/WORKFLOW.md`

## Context

`pikachu-rl-dev-backend-1` entered a crash loop (`ModuleNotFoundError: prometheus_client`) after a merge that added `backend/app/metrics.py` without rebuilding the Docker image. No team member noticed — the dev environment was functionally down while everyone assumed green. The failure mode was silent: a module import at process start kills the container before any API check can succeed, so only a direct container-status query surfaces the problem.

## Decision

Every person who merges to `dev` owns the post-merge health check and performs it immediately. Mandatory sequence:

1. `docker ps --filter name=pikachu-rl-dev` — STATUS must read `(healthy)`. `(health: starting)` → wait 30 s and re-check.
2. `curl -s http://localhost:8001/api/health` — must return `{"status": "ok"}`.
3. On failure: `docker logs pikachu-rl-dev-backend-1 --tail 30` and report to PM.

Any merge that adds a new Python dependency (edit to `pyproject.toml`) additionally requires a Docker image rebuild (`docker compose -f docker-compose.dev.yml build backend` + `up -d backend`) **before** the health check. The author of the merge, not DevOps, is responsible.

## Consequences

- Merge authors can no longer "hand off" deploy verification — the check is part of the merge unit of work.
- CI cannot fully substitute: the failure mode is a runtime import error that only surfaces when the production image actually starts. Automated health probes help but don't remove author responsibility.
- If DevOps adds a pre-deploy sanity gate later (image-build + boot smoke), this ADR is revisited for possible relaxation to CI-only; until then, manual verification stands.
