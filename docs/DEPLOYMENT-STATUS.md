# Deployment Status

> Last updated: 2026-04-12

## Environment Overview

| Environment | Version | Commit | Tag | Status | Updated |
|-------------|---------|--------|-----|--------|---------|
| **dev** | 0.2.0-dev | `2043e44` | — | Active development | 2026-04-12 |
| **qa** | 0.2.0 | `d8fc62e` | `v0.2.0` | Awaiting QA deploy | 2026-04-12 |
| **prod** | 0.1.0 | `41f4fdb` | — | Running (initial) | 2026-04-11 |

## Ports

| Environment | Backend | Frontend | MongoDB |
|-------------|---------|----------|---------|
| dev | :8001 | :3000 | :27018 |
| qa | :8002 | :3001 | :27019 |
| prod | :8000 | :5173 | :27017 |

## Release History

| Version | QA Deploy | QA Verified | Prod Deploy | Release Note |
|---------|-----------|-------------|-------------|--------------|
| 0.2.0 | Pending | — | — | [v0.2.0-qa](releases/v0.2.0-qa.md) |
| 0.1.0 | — | — | 2026-04-11 | Initial structure |

## Pending Actions

- [ ] DevOps: Deploy v0.2.0 to QA environment ([#6](https://github.com/shyoon-devops/pikachu-volleyball-rl/issues/6))
- [ ] QA Engineer: Verify v0.2.0 on QA environment
- [ ] PM: Approve prod deployment after QA pass
- [ ] DevOps: Deploy to prod after PM approval

## Branch State

```
dev   2043e44  ← active development (all teams merged)
qa    d8fc62e  ← v0.2.0 release commit (dev + VERSION/CHANGELOG)
prod  41f4fdb  ← previous state (awaiting v0.2.0 promotion)
```
