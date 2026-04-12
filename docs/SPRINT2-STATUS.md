# Sprint 2 (v0.2.2) — Status Report

> **Sprint Start**: TBD (Sprint 1 QA 검증 완료 후 착수) | **Target End**: Start + 5d
> **Last Updated**: 2026-04-12
> **Previous Sprint**: [sprint1-v0.2.1 tracker](sprint-tracking/sprint1-v0.2.1.md)

---

## Goal

품질 강화 + UX 고도화 — 테스트 커버리지, 로깅/관측성, API 캐싱, 차트 개선, 자동 백업.

Sprint 1(안정성)이 "터지지 않게" 만들었다면, Sprint 2는 "들여다볼 수 있게" + "빠르고 정리된 모습"을 만든다.

---

## Scope — 7 items

| # | Issue | Item | Team | Effort | Status | Commit |
|---|-------|------|------|--------|--------|--------|
| 1 | [#30](https://github.com/shyoon-devops/pikachu-volleyball-rl/issues/30) | FE-2: MetricsChart Smoothing + Zoom | Frontend | 1d | ⬜ 미착수 | — |
| 2 | [#31](https://github.com/shyoon-devops/pikachu-volleyball-rl/issues/31) | BE-2: API Caching + Unified Pagination | Backend | 0.5d | ⬜ 미착수 | — |
| 3 | [#32](https://github.com/shyoon-devops/pikachu-volleyball-rl/issues/32) | BE-3: Structured Logging + Health Depth | Backend | 0.5d | ⬜ 미착수 | — |
| 4 | [#33](https://github.com/shyoon-devops/pikachu-volleyball-rl/issues/33) | BE-5: Backend Coverage ≥ 80% | Backend | 1d | ⬜ 미착수 | — |
| 5 | [#34](https://github.com/shyoon-devops/pikachu-volleyball-rl/issues/34) | QA-3: FastAPI TestClient Integration | QA | 1d | ⬜ 미착수 | — |
| 6 | [#35](https://github.com/shyoon-devops/pikachu-volleyball-rl/issues/35) | DO-3: MongoDB Automated Backup | DevOps | 0.5d | ⬜ 미착수 | — |
| 7 | [#4](https://github.com/shyoon-devops/pikachu-volleyball-rl/issues/4) | Frontend Test Coverage 보강 | Frontend | 1d | ⬜ 미착수 | — |

**Status Legend**: ⬜ 미착수 · 🔵 진행중 · 🟡 검증중 · ✅ 완료 · 🔴 블로커

---

## Team Assignments

### Backend Engineer (3 items, 2d)

```
Day 1  BE-2 [⬜] BE-3 [⬜]
Day 2  BE-5 [⬜] (coverage push + CI gate)
Day 3  자체 테스트 + 통합 검증
```

**Files to touch:**
- `backend/app/api/routes.py`, `backend/app/services/*`
- `backend/app/logging.py` (신규), `backend/app/schemas/pagination.py` (신규)
- `backend/tests/*` (커버리지 보강)
- `pyproject.toml`, `.github/workflows/ci.yml`

### Frontend Engineer (2 items, 2d)

```
Day 1  FE-2 [⬜] (스무딩 + 줌)
Day 2  #4 FE Test Coverage [⬜]
Day 3  통합 검증
```

**Files to touch:**
- `frontend/src/components/dashboard/MetricsChart.tsx`
- `frontend/src/lib/smoothing.ts` (신규)
- `frontend/src/**/__tests__/*` (신규 테스트 다수)

### QA Engineer (1 item, 1d + 전체 검증)

```
Day 1  QA-3 [⬜] (TestClient integration suite)
Day 2  대기 + Sprint 1 v0.2.1 QA 검증 완결 지원
Day 3  Sprint 2 전체 검증 + QA 리포트
```

### DevOps Engineer (1 item, 0.5d + 배포)

```
Day 1  DO-3 [⬜] (MongoDB 백업) + 대기
Day 2  v0.2.2 QA 배포
Day 3  prod 배포 (PM 승인 후)
```

---

## Dependencies & Risks

| 유형 | 항목 | 영향 | 대응 |
|------|------|------|------|
| Blocker | Sprint 1 QA 검증 미완료 | Sprint 2 착수 지연 | QA Engineer 검증 리포트 우선 |
| Dep | BE-3 로그 스키마 결정 | DO-1(Sprint 3 모니터링)에 영향 | BE-3에서 선제적으로 Prometheus 호환 라벨 협의 |
| Risk | BE-5 80% 커버리지 도달 실패 | CI gate 실패 → 스프린트 지연 | 현재 커버리지 측정부터 → 갭 식별 → 우선순위 |
| Risk | DO-3 백업 공간 부족 | 백업 실패 | 로테이션 정책 엄격 적용, 디스크 모니터링 |

---

## Metrics (Sprint 완료 기준)

- [ ] Backend coverage ≥ **80%** (전체 line coverage)
- [ ] FE 테스트 파일 수 ≥ **11개** (현재 4 + 추가 7)
- [ ] 전 API 엔드포인트 페이지네이션 envelope 통일
- [ ] JSON 구조화 로그 출력 확인 + `correlation_id` 삽입
- [ ] MongoDB 백업 아카이브 ≥ 1개 정상 생성
- [ ] CI 파이프라인 실패율 < 5% (flaky test 억제)

자세한 프로젝트 메트릭: [docs/METRICS.md](METRICS.md)

---

## Daily Log

### Pending
Sprint 2 킥오프 대기 — Sprint 1 (v0.2.1) QA 검증 + prod 배포 사이클 완료 후 착수.

---

## Blockers & Risks Log

| Date | Item | Issue | Impact | Resolution |
|------|------|-------|--------|------------|
| — | — | — | — | — |

---

## Release Criteria — v0.2.2

- [ ] 7개 항목 모두 dev 머지 + QA 검증 완료
- [ ] Backend coverage ≥ 80% (CI gate pass)
- [ ] Frontend 커버리지 의미있는 증가 (4 → 11+ 파일)
- [ ] 구조화 로그 스테이징에서 파싱 가능 검증
- [ ] 백업 drill 1회 수행 기록
- [ ] QA 검증 리포트 PASS
- [ ] PM prod 배포 승인
- [ ] v0.2.2 태그 + prod → main 머지 + `v0.2.2` tag

---

## Links

- Sprint 전체 계획: [docs/proposals/SPRINT-PLAN-23-ITEMS.md](proposals/SPRINT-PLAN-23-ITEMS.md)
- Sprint 1 추적: [docs/sprint-tracking/sprint1-v0.2.1.md](sprint-tracking/sprint1-v0.2.1.md)
- 배포 상태: [docs/DEPLOYMENT-STATUS.md](DEPLOYMENT-STATUS.md)
- 품질 메트릭: [docs/METRICS.md](METRICS.md)
- 릴리스 노트 템플릿: [docs/releases/TEMPLATE.md](releases/TEMPLATE.md)
