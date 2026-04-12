# Deployment Status

> Last updated: 2026-04-12

## Environment Overview

| Environment | Version | Commit | Tag | Status | Updated |
|-------------|---------|--------|-----|--------|---------|
| **dev** | 0.2.0-dev | `f4b4dfa` | — | Active development (Sprint 1) | 2026-04-12 |
| **qa** | 0.2.0 | `d8fc62e` | `v0.2.0` | Awaiting QA deploy | 2026-04-12 |
| **prod** | 0.1.0 | `41f4fdb` | `v0.1.0` | Running (main merged) | 2026-04-12 |
| **main** | 0.1.0 | `fdc41de` | `v0.1.0` | Prod mirror (tagged) | 2026-04-12 |

## Ports

| Environment | Backend | Frontend | MongoDB |
|-------------|---------|----------|---------|
| dev | :8001 | :3000 | :27018 |
| qa | :8002 | :3001 | :27019 |
| prod | :8000 | :5173 | :27017 |

## Release History

| Version | QA Deploy | QA Verified | Prod Deploy | Main Merge | Tag | Release Note |
|---------|-----------|-------------|-------------|------------|-----|--------------|
| 0.2.0 | Pending | — | — | — | `v0.2.0` (qa) | [v0.2.0-qa](releases/v0.2.0-qa.md) |
| 0.1.0 | — | — | 2026-04-11 | 2026-04-12 (`fdc41de`) | `v0.1.0` | Initial structure |

## Pending Actions

- [ ] DevOps: Deploy v0.2.0 to QA environment ([#6](https://github.com/shyoon-devops/pikachu-volleyball-rl/issues/6))
- [ ] QA Engineer: Verify v0.2.0 on QA environment
- [ ] PM: Approve prod deployment after QA pass
- [ ] DevOps: Deploy to prod after PM approval
- [ ] **PM: prod → main 머지 + v0.2.0 태그** (prod v0.2.0 배포 완료 후 필수)
- [ ] Sprint 1 잔여 버그 수정 완료 후 v0.2.1 릴리스 준비 ([tracker](sprint-tracking/sprint1-v0.2.1.md))

## Completed

- [x] prod → main 머지 + v0.1.0 태그 (2026-04-12, `fdc41de`)

## Branch State

```
dev   f4b4dfa  ← active development (trainer PR #28 merged, evaluator sync)
qa    d8fc62e  ← v0.2.0 release commit (tagged v0.2.0)
prod  41f4fdb  ← current production (awaiting v0.2.0 promotion)
main  fdc41de  ← prod mirror with v0.1.0 tag (merged 2026-04-12)
```
