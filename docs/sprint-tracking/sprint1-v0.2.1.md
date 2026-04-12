# Sprint 1 (v0.2.1) Progress Tracker

> **Sprint Start**: 2026-04-12 | **Target End**: 2026-04-15 (3d dev + QA)
> **Last Updated**: 2026-04-12 (code complete — 20 items dev-merged, 11 more issues closed, QA pending)

---

## Status Legend

| Icon | Status | Description |
|------|--------|-------------|
| ⬜ | 미착수 | Not started |
| 🔵 | 진행중 | In progress |
| 🟡 | 검증중 | Code complete, under QA review |
| ✅ | 완료 | Done and verified |
| 🔴 | 블로커 | Blocked |

---

## CRITICAL Security (Backend Engineer)

| # | Issue | Item | Status | Assignee | PR | Notes |
|---|-------|------|--------|----------|-----|-------|
| 1 | ~~[#9](https://github.com/shyoon-devops/pikachu-volleyball-rl/issues/9)~~ | SEC-1: Path Traversal Fix | 🟡 검증중 | Backend | `10c9f1d` | dev 머지, QA v0.2.1 확인 대기 |
| 2 | ~~[#10](https://github.com/shyoon-devops/pikachu-volleyball-rl/issues/10)~~ | SEC-2: CORS Origin 분리 | 🟡 검증중 | Backend + DevOps | `10c9f1d` | dev 머지, QA v0.2.1 확인 대기 |
| 3 | ~~[#11](https://github.com/shyoon-devops/pikachu-volleyball-rl/issues/11)~~ | SEC-3: Rate Limiting 추가 | 🟡 검증중 | Backend | `10c9f1d` | dev 머지, QA v0.2.1 확인 대기 |

## BLOCKER (Trainer + AI Engineer)

| # | Issue | Item | Status | Assignee | PR | Notes |
|---|-------|------|--------|----------|-----|-------|
| 4 | ~~[#12](https://github.com/shyoon-devops/pikachu-volleyball-rl/issues/12)~~ | TR-4: Training Session Protection | 🟡 검증중 | Trainer + AI | PR #28 / `6e8ea3e` | dev 머지, QA v0.2.1 확인 대기 |

## HIGH Bugs (Cross-team)

| # | Issue | Item | Status | Assignee | PR | Notes |
|---|-------|------|--------|----------|-----|-------|
| 5 | ~~[#13](https://github.com/shyoon-devops/pikachu-volleyball-rl/issues/13)~~ | BUG-1: Queue Unbounded (OOM risk) | 🟡 검증중 | Backend | `5d143ae` | dev 머지, QA v0.2.1 확인 대기 |
| 6 | ~~[#14](https://github.com/shyoon-devops/pikachu-volleyball-rl/issues/14)~~ | BUG-2: Health Check False OK | 🟡 검증중 | Backend | `5d143ae` | dev 머지, QA v0.2.1 확인 대기 |
| 7 | ~~[#15](https://github.com/shyoon-devops/pikachu-volleyball-rl/issues/15)~~ | BUG-3: Training Status Incomplete | 🟡 검증중 | Trainer | `5c30671` | dev 머지, QA v0.2.1 확인 대기 |
| 8 | ~~[#16](https://github.com/shyoon-devops/pikachu-volleyball-rl/issues/16)~~ | BUG-4: Heartbeat No Pong Protocol | 🟡 검증중 | Backend + FE | `5d143ae` | dev 머지, QA v0.2.1 확인 대기 |
| 9 | ~~[#17](https://github.com/shyoon-devops/pikachu-volleyball-rl/issues/17)~~ | BUG-5: Models/Replays No Pagination | 🟡 검증중 | Backend | `07c36bd` | dev 머지, QA v0.2.1 확인 대기 |
| 10 | ~~[#18](https://github.com/shyoon-devops/pikachu-volleyball-rl/issues/18)~~ | BUG-6: Game Result Save Data Loss | 🟡 검증중 | Backend | `5d143ae` | dev 머지, QA v0.2.1 확인 대기 |
| 11 | ~~[#19](https://github.com/shyoon-devops/pikachu-volleyball-rl/issues/19)~~ | BUG-7: WS Reconnection Missing | 🟡 검증중 | Frontend | `2338102` | dev 머지, QA v0.2.1 확인 대기 |

## Sprint 1 Enhancement Items

| # | Issue | Item | Status | Assignee | PR | Notes |
|---|-------|------|--------|----------|-----|-------|
| 12 | ~~[#20](https://github.com/shyoon-devops/pikachu-volleyball-rl/issues/20)~~ | BE-1: WS Heartbeat + Backpressure | 🟡 검증중 | Backend | `3f8abb8` | dev 머지, QA v0.2.1 확인 대기 |
| 13 | ~~[#21](https://github.com/shyoon-devops/pikachu-volleyball-rl/issues/21)~~ | BE-4: Input Validation | 🟡 검증중 | Backend | `3f8abb8` | dev 머지, QA v0.2.1 확인 대기 |
| 14 | ~~[#22](https://github.com/shyoon-devops/pikachu-volleyball-rl/issues/22)~~ | FE-3: GameCanvas Responsive | 🟡 검증중 | Frontend | `2338102` | dev 머지, QA v0.2.1 확인 대기 |
| 15 | ~~[#23](https://github.com/shyoon-devops/pikachu-volleyball-rl/issues/23)~~ | FE-1: Replay Keyboard Shortcuts | 🟡 검증중 | Frontend | `830278b` | dev 머지, QA v0.2.1 확인 대기 |
| 16 | ~~[#24](https://github.com/shyoon-devops/pikachu-volleyball-rl/issues/24)~~ | FE-5: A11y Accessibility | 🟡 검증중 | Frontend | `2338102` | dev 머지, QA v0.2.1 확인 대기 |
| 17 | ~~[#25](https://github.com/shyoon-devops/pikachu-volleyball-rl/issues/25)~~ | QA-2: CI/CD Test Pipeline | 🟡 검증중 | DevOps | `9d257c9` (PR #29) | dev 머지, QA v0.2.1 확인 대기 |
| 18 | ~~[#26](https://github.com/shyoon-devops/pikachu-volleyball-rl/issues/26)~~ | QA-4: Security Auto-Scan | 🟡 검증중 | DevOps | `9d257c9` (PR #29) | dev 머지, QA v0.2.1 확인 대기 |
| 19 | ~~[#27](https://github.com/shyoon-devops/pikachu-volleyball-rl/issues/27)~~ | Design Review: Sprite Rendering | 🟡 검증중 | Designer | `ede4e34` | dev 머지, QA v0.2.1 확인 대기 |

---

## Team Progress Dashboard

### Backend Engineer (10 items)

```
Day 1  SEC-1 [⬜] SEC-2 [⬜] SEC-3 [⬜] BUG-2 [⬜]
Day 2  BE-1 [⬜] BUG-1 [⬜] BUG-4 [⬜] BUG-5 [⬜] BUG-6 [⬜]
Day 3  BE-4 [⬜] 자체 테스트
```

Progress: 0/10 ████████████████████ 0%

### Trainer + AI Engineer (2 items)

```
Day 1  TR-4 [⬜] (공동 작업)
Day 2  BUG-3 [⬜] + 통합 검증
```

Progress: 0/2 ████████████████████ 0%

### Frontend Engineer (5 items)

```
Day 1  BUG-7 [⬜] FE-3 [⬜]
Day 2  FE-1 [⬜] FE-5 [⬜]
Day 3  BUG-4/FE [⬜] 자체 테스트
```

Progress: 0/5 ████████████████████ 0%

### QA Engineer (2 items + 전체 검증)

```
Day 1  QA-2 [⬜]
Day 2  QA-4 [⬜] + SEC 검증
Day 3  전체 검증 + QA 리포트
```

Progress: 0/2 ████████████████████ 0%

### DevOps Engineer (1 item)

```
Day 1  QA Deploy [⬜] + CORS env config [⬜]
Day 2  대기 + 이슈 대응
```

Progress: 0/1 ████████████████████ 0%

---

## Overall Sprint Progress

```
Total Items:   19 (Sprint 1 expanded + design review)
Completed:      0 (QA 검증 후 ✅)
Under Review:  19 (전 항목 dev 머지 완료, QA v0.2.1 배포 및 검증 대기)
In Progress:    0
Not Started:    0
Blocked:        0

Overall: ████████████████████ 100% 코드 완료 · QA 검증 0%
```

---

## Daily Log

### 2026-04-12
- Sprint 1 승인, 작업 할당 문서 배포 완료
- GitHub Issues #9~#26 생성
- 각 팀 워크트리에 SPRINT1-ASSIGNMENT.md 전달
- **dev 머지 1차**: SEC-1/2/3 (10c9f1d), TR-4 (PR #28), BUG-3 (5c30671), BUG-5 (07c36bd), BE-1 + BE-4 (3f8abb8), FE-1 (830278b)
- **dev 머지 2차**: BUG-1/2/4/6 (5d143ae, 8565887), BUG-7 + FE-3 + FE-5 (2338102), Design Review #27 (ede4e34), QA-2 + QA-4 (9d257c9, PR #29), 미머지 브랜치 전부 통합 (devops/trainer/evaluator)
- **이슈 CLOSED (20건 누적)**:
  - 1차 9건: #9, #10, #11, #12, #15, #17, #20, #21, #23
  - 2차 11건: #13, #14, #16, #18, #19, #22, #24, #25, #26, #27, #3
- **prod → main 머지 완료**: `fdc41de` — `v0.1.0` 태그 부착 및 push
- **dev health check 통과**: `docker ps` = healthy, `/api/health` = 200 OK
- CHANGELOG.md에 [0.2.0] + [0.2.1] 상세 섹션 추가

---

## Blockers & Risks

| Date | Item | Issue | Impact | Resolution |
|------|------|-------|--------|------------|
| — | — | — | — | — |

---

## QA Verification Log

| Date | Item | Tester | Result | Notes |
|------|------|--------|--------|-------|
| — | — | — | — | — |

---

## Release Criteria

- [ ] All CRITICAL security fixes verified (SEC-1/2/3)
- [ ] BLOCKER resolved (TR-4)
- [ ] All HIGH bugs fixed (BUG-1~7)
- [ ] All enhancement items complete (BE-1, BE-4, FE-1/3/5, QA-2/4)
- [ ] Backend test coverage ≥ 80%
- [ ] CI/CD pipeline operational
- [ ] Security scan passing
- [ ] QA 검증 리포트 PASS
- [ ] PM prod 배포 승인
- [ ] Version: 0.2.1 tagged
