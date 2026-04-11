# Sprint Plan — 23건 전량 Prod 배포 계획

> **Date**: 2026-04-12 | **Policy**: 23건 전부 prod 반영 전까지 추가 제안 금지

---

## Sprint 1: 안정성 + 기반 (v0.2.1)

**목표**: prod 훈련 보호, 인프라 안정화, 기본 UX 개선
**기간**: 3일 (4개 팀 병렬)

| # | ID | Team | Task | Effort | Deps |
|---|-----|------|------|--------|------|
| 1 | TR-4 | Trainer+BE | Training Session Protection **(BLOCKER)** | 0.5d | — |
| 2 | BE-1 | Backend | WebSocket Heartbeat + Backpressure | 0.5d | — |
| 3 | BE-4 | Backend | 입력 검증 + Rate Limiting | 0.5d | — |
| 4 | FE-3 | Frontend | GameCanvas 반응형 스케일링 | 0.5d | — |
| 5 | FE-1 | Frontend | Replay 키보드 단축키 | 0.5d | — |
| 6 | FE-5 | Frontend | 접근성 A11y 개선 | 0.5d | — |
| 7 | QA-2 | QA | CI/CD 테스트 파이프라인 | 1d | — |
| 8 | QA-4 | QA | 보안 자동 스캔 | 0.5d | — |

**팀별 일정:**

```
         Day 1              Day 2              Day 3
Trainer  [TR-4 ██████████]  (완료)
Backend  [TR-4 █][BE-1 ██]  [BE-4 █████████]   (완료)
Frontend [FE-3 ██][FE-1 █]  [FE-5 █████████]   (완료)
QA       [QA-2 ██████████]  [QA-4 █████████]   (완료)
DevOps   [v0.2.0 QA배포 ██] [대기 ██████████]  (완료)
```

**사이클**: 개발 3일 → QA 검증 1일 → PM prod 승인 → DevOps 배포 → **v0.2.1 릴리스**

---

## Sprint 2: 품질 강화 + UX 고도화 (v0.2.2)

**목표**: 테스트 커버리지, 로깅, 캐싱, 차트 개선, 백업
**기간**: 3일

| # | ID | Team | Task | Effort | Deps |
|---|-----|------|------|--------|------|
| 9 | FE-2 | Frontend | MetricsChart 스무딩/줌 | 1d | — |
| 10 | BE-2 | Backend | API 캐싱 + 페이지네이션 통일 | 0.5d | — |
| 11 | BE-3 | Backend | 구조화 로깅 + Health Check | 0.5d | — |
| 12 | BE-5 | Backend | 테스트 커버리지 80%+ | 1d | — |
| 13 | QA-3 | QA | FastAPI TestClient 통합 테스트 보강 | 1d | — |
| 14 | DO-3 | DevOps | MongoDB 자동 백업 | 0.5d | — |

**팀별 일정:**

```
         Day 1              Day 2              Day 3
Backend  [BE-2 ██][BE-3 █]  [BE-5 ██████████]  (완료)
Frontend [FE-2 ██████████]  (완료)
QA       [QA-3 ██████████]  (완료)
DevOps   [DO-3 █████](완료) [대기]
```

**사이클**: 개발 3일 → QA 검증 1일 → prod 배포 → **v0.2.2 릴리스**

---

## Sprint 3: RL 고도화 + 모니터링 (v0.3.0)

**목표**: Self-play 파이프라인, 모니터링 스택, 고급 기능
**기간**: 5~7일 (가장 큰 스프린트)

| # | ID | Team | Task | Effort | Deps |
|---|-----|------|------|--------|------|
| 15 | TR-1 | Trainer | Self-play 훈련 파이프라인 | 2~3d | BE API |
| 16 | TR-3 | Trainer | Position-Based Reward Shaping | 1d | — |
| 17 | TR-2 | Trainer | Adaptive Curriculum (L5→self-play) | 1~2d | TR-1 |
| 18 | FE-4 | Frontend | Multi-run 세션 비교 | 2~3d | BE API |
| 19 | DO-1 | DevOps | 모니터링 스택 (Prometheus+Grafana) | 2~3d | — |
| 20 | QA-1 | QA | 부하 테스트 자동화 | 2d | — |
| 21 | BE-6 | Backend | 평가 병렬화 | 0.5d | — |

**팀별 일정:**

```
         Day 1-2            Day 3-4            Day 5-7
Trainer  [TR-3 ████████]    [TR-1 ████████████████████████████]
         (reward shaping)   [TR-2 ████████████] (TR-1 완료 후)
Backend  [BE API for TR-1]  [BE-6 ███][FE-4 API support]
Frontend [대기]              [FE-4 ████████████████████████████]
DevOps   [DO-1 ████████████████████████████████████████████████]
QA       [QA-1 ████████████████████████]
```

**사이클**: 개발 5~7일 → QA 검증 2일 → prod 배포 → **v0.3.0 릴리스**

---

## Sprint 4: 마무리 (v0.3.1)

**목표**: 나머지 2건 + 전체 폴리싱
**기간**: 2~3일

| # | ID | Team | Task | Effort | Deps |
|---|-----|------|------|--------|------|
| 22 | DO-2 | DevOps | 컨테이너 로그 뷰어 (Dozzle) | 0.5d | — |
| 23 | FE-6 | Frontend | Self-play 대전 시각화 | 2d | TR-1 |

**사이클**: 개발 2~3일 → QA 검증 1일 → prod 배포 → **v0.3.1 릴리스** → **23건 전량 완료**

---

## 전체 타임라인

```
Sprint 1 (v0.2.1)  ████████░  3d dev + 1d QA + deploy  =  ~5d  | 8건
Sprint 2 (v0.2.2)  ██████░    3d dev + 1d QA + deploy  =  ~5d  | 6건
Sprint 3 (v0.3.0)  ██████████████░  5-7d dev + 2d QA   = ~10d  | 7건
Sprint 4 (v0.3.1)  █████░     2-3d dev + 1d QA         =  ~4d  | 2건
                                                         ------
                                              Total:     ~24일  | 23건
```

## 릴리스 사이클 (매 스프린트)

```
1. PM이 스프린트 작업 할당 전달
2. 팀별 개발 (feature branches → dev 머지)
3. PM이 버전 생성 (VERSION, CHANGELOG, tag)
4. DevOps가 QA 환경 배포
5. QA Engineer가 검증 리포트 작성
6. PM이 prod 배포 승인 판단
7. 승인 시 DevOps → Project Manager에게 '배포 요청' → 최종 승인
8. Prod 배포 완료 → 다음 스프린트 시작
```

## 추적 규칙

- **추가 제안 금지**: 23건 전부 prod 반영 전까지
- **변경 요청**: PM을 통해서만 (우선순위 재조정 가능)
- **블로커 발생 시**: 즉시 PM에게 보고, 스프린트 계획 조정
- **각 스프린트 완료 시**: DEPLOYMENT-STATUS.md 업데이트, 릴리스 노트 아카이빙
