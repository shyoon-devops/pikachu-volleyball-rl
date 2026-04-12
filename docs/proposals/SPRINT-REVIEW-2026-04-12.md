# Sprint Proposal Review — 2026-04-12

> **Reviewer**: Product Manager | **Total Proposals**: 23건 (5개 팀)
> **Status**: PM 검토 완료, Project Manager 최종 승인 대기

---

## CRITICAL / BLOCKER

### TR-4. Training Session Protection (Trainer)

| 항목 | 내용 |
|------|------|
| 긴급도 | **BLOCKER** — prod 훈련이 외부 간섭으로 중단됨 |
| 공수 | 0.5~1일 |
| 의존성 | Backend WebSocket handler 수정 필요 |

**PM 판정: 즉시 착수**

prod 환경에서 진행 중인 훈련이 외부 간섭으로 중단되는 문제는 프로젝트의 핵심 가치(RL 훈련)를 직접 위협합니다. 다음을 구현해야 합니다:
- WebSocket `training:start` 중복 호출 시 기존 세션 보호 (이미 `5c30671`에서 crash 방지는 됐지만, 세션 잠금이 필요)
- 훈련 중 상태를 `locked` 로 관리, 명시적 `training:stop` 만 허용
- 긴급 중지는 별도 `training:force_stop` + 확인 절차

**할당**: Trainer + Backend Engineer 공동 작업. 즉시 시작.

---

## 우선순위 통합 매트릭스

### Tier 1: 현재 스프린트 (v0.2.x) — 즉시~3일

| # | Team | Proposal | Priority | Effort | Deps | 판정 |
|---|------|----------|----------|--------|------|------|
| TR-4 | Trainer | Training Session Protection | **BLOCKER** | 0.5d | BE | **즉시 착수** |
| BE-1 | Backend | WebSocket Heartbeat + Backpressure | HIGH | 0.5d | — | ✅ 승인 |
| BE-4 | Backend | 입력 검증 + Rate Limiting | HIGH | 0.5d | — | ✅ 승인 |
| FE-3 | Frontend | GameCanvas 반응형 스케일링 | P1 | 0.5d | — | ✅ 승인 |
| FE-1 | Frontend | Replay 키보드 단축키 | P1 | 0.5d | — | ✅ 승인 |
| FE-5 | Frontend | 접근성 A11y 개선 | P2↑ | 0.5d | — | ✅ 승인 |
| QA-2 | QA | CI/CD 테스트 파이프라인 | P1 | 1d | — | ✅ 승인 |
| QA-4 | QA | 보안 자동 스캔 | P1 | 0.5d | — | ✅ 승인 |

**Tier 1 합계**: 4.5일 (4개 팀 병렬 시 ~2일)

### Tier 2: 현재 스프린트 후반 (v0.2.x) — QA 통과 후

| # | Team | Proposal | Priority | Effort | Deps | 판정 |
|---|------|----------|----------|--------|------|------|
| FE-2 | Frontend | MetricsChart 스무딩/줌 | P1 | 1d | — | ✅ v0.2.1 |
| BE-2 | Backend | API 캐싱 + 페이지네이션 통일 | MED | 0.5d | — | ✅ 승인 |
| BE-3 | Backend | 구조화 로깅 + Health Check | MED | 0.5d | — | ✅ 승인 |
| BE-5 | Backend | 테스트 커버리지 80%+ | MED | 1d | — | ✅ 승인 |
| QA-3 | QA | FastAPI TestClient 통합 테스트 보강 | P2 | 1d | — | ✅ 승인 |
| DO-3 | DevOps | MongoDB 자동 백업 | MED | 0.5d | — | ✅ 승인 |

**Tier 2 합계**: 4.5일

### Tier 3: 다음 스프린트 백로그 (v0.3.0)

| # | Team | Proposal | Priority | Effort | Deps | 판정 |
|---|------|----------|----------|--------|------|------|
| TR-1 | Trainer | Self-play 훈련 파이프라인 | P2 | 2~3d | BE API | ⏸️ v0.3.0 |
| TR-2 | Trainer | Adaptive Curriculum (L5→self-play) | P2 | 1~2d | TR-1 | ⏸️ TR-1 이후 |
| TR-3 | Trainer | Position-Based Reward Shaping | P2 | 1d | — | ⏸️ v0.3.0 |
| FE-4 | Frontend | Multi-run 세션 비교 | P2 | 2~3d | BE API | ⏸️ v0.3.0 |
| BE-6 | Backend | 평가 병렬화 | LOW | 0.5d | — | ⏸️ v0.3.0 |
| DO-1 | DevOps | 모니터링 스택 (Prometheus+Grafana) | P2 | 2~3d | — | ⏸️ v0.3.0 |
| DO-2 | DevOps | 컨테이너 로그 뷰어 (Dozzle) | P3 | 0.5d | — | ⏸️ v0.3.0 |
| QA-1 | QA | 부하 테스트 자동화 | P3 | 2d | — | ⏸️ v0.3.0 |
| FE-6 | Frontend | Self-play 대전 시각화 | P3 | 2d | TR-1, BE | ⏸️ v0.3.0+ |

---

## 팀별 할당 (현재 스프린트)

### Trainer (즉시)
```
Day 1: TR-4 Training Session Protection (BLOCKER, BE와 공동)
```

### Backend Engineer (즉시)
```
Day 1 AM: TR-4 공동 작업 (WebSocket handler 수정)
Day 1 PM: BE-1 WebSocket Heartbeat + Backpressure
Day 2 AM: BE-4 입력 검증 + Rate Limiting
Day 2 PM: BE-2 API 캐싱 + 페이지네이션
Day 3:    BE-3 구조화 로깅 + BE-5 테스트 커버리지
```

### Frontend Engineer
```
Day 1 AM: FE-3 GameCanvas 반응형 (0.5d)
Day 1 PM: FE-1 Replay 키보드 단축키 (0.5d)
Day 2 AM: FE-5 A11y 접근성 (0.5d)
Day 2 PM ~ Day 3: FE-2 MetricsChart 스무딩/줌 (1d)
```

### QA Engineer
```
Day 1: QA-2 CI/CD 테스트 파이프라인 (1d)
Day 2 AM: QA-4 보안 자동 스캔 (0.5d)
Day 2 PM ~ Day 3: QA-3 통합 테스트 보강 (1d)
```

### DevOps Engineer
```
Day 1: v0.2.0 QA 환경 배포 (Issue #6)
Day 2: DO-3 MongoDB 자동 백업 (0.5d)
Day 2 PM: 기존 2-server 아키텍처 작업 계속
```

---

## 제안 간 의존성 그래프

```
TR-4 (BLOCKER) ──→ BE-1 (heartbeat) ──→ 안정적 WS 통신
                                    
TR-1 (self-play) ──→ TR-2 (adaptive curriculum)
                 └──→ FE-4 (multi-run comparison)
                 └──→ FE-6 (self-play visualization)

QA-2 (CI pipeline) ──→ QA-4 (security scan in CI)
                   └──→ BE-5 (coverage gate in CI)
```

---

## PM 종합 의견

1. **TR-4는 블로커**입니다. prod 훈련 보호가 안 되면 다른 기능이 아무리 좋아도 의미가 없습니다. Trainer + Backend 즉시 착수.

2. **인프라 안정성 우선**: BE-1(heartbeat), BE-4(rate limiting), QA-2(CI pipeline), QA-4(security scan)을 현재 스프린트에 넣는 이유는 v0.2.0이 QA/prod로 가기 전에 기반을 단단히 해야 하기 때문입니다.

3. **UX 개선 4건**(FE-1,2,3,5)은 공수가 작고(총 2.5일) 사용자 경험 향상 효과가 즉각적이라 현재 스프린트에 포함.

4. **Self-play 관련**(TR-1,2, FE-4,6)은 v0.3.0으로 일괄 보류. 아직 Bot 대전 기반 훈련도 충분히 검증되지 않은 상태에서 self-play를 도입하면 복잡도만 올라갑니다.

5. **모니터링**(DO-1,2)은 가치 있지만 현재 스프린트에 넣기엔 공수가 큼. v0.3.0에서 DevOps 주력 작업으로.

6. 앞으로 모든 제안은 이 문서에 누적 관리합니다. 팀별로 올라오면 여기에 추가하고 상의 후 승인합니다.
