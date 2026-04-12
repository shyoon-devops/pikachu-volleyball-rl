# Project Quality Metrics

> **Purpose**: 이 프로젝트가 "좋은 상태"인지 측정할 수 있는 기준 정의. 릴리스 gate, 스프린트 완료 기준, 회고 재료로 사용.
> **Last Updated**: 2026-04-12

---

## 1. Code Quality

### 1.1 Test Coverage

| Scope | Target | Measured By | Gate |
|-------|--------|-------------|------|
| Backend line coverage | ≥ 80% | `pytest --cov=backend --cov-report=term` | CI 실패 |
| Backend branch coverage | ≥ 70% | `pytest --cov-branch` | 경고 |
| Frontend statement coverage | ≥ 60% | `vitest run --coverage` | 경고 |
| Critical path (game engine, RL env, trainer) | ≥ 90% | 동일 | CI 실패 |

> **규칙**: 테스트 없는 코드는 머지 금지. Mutation 테스트는 향후 과제.

### 1.2 Static Analysis

| Tool | Scope | Gate |
|------|-------|------|
| ruff | Python 전체 | CI 실패 |
| mypy | `backend/` strict 설정 | 경고 (점진 이행) |
| eslint | Frontend | CI 실패 |
| tsc --noEmit | Frontend strict | CI 실패 |

### 1.3 Complexity & Size

| Metric | Target | Note |
|--------|--------|------|
| Function length | ≤ 50 lines | 넘으면 분리 권장 |
| File length | ≤ 800 lines | 넘으면 모듈 분할 |
| Cyclomatic complexity | ≤ 10 per function | radon 측정 |
| Max nesting | ≤ 4 levels | 초과 시 early return |

---

## 2. Security

### 2.1 Automated Scans

| Tool | Scope | Frequency | Gate |
|------|-------|-----------|------|
| bandit | Python 소스 | CI on push | HIGH 이슈 → 실패 |
| npm audit | Frontend deps | CI on push | HIGH 이슈 → 실패 |
| pip-audit | Python deps | CI weekly | HIGH 이슈 → 실패 |
| trivy (컨테이너) | Docker images | Release cut | CRITICAL → 실패 |

### 2.2 Security Checklist (릴리스별 필수)

- [ ] CORS 허용 오리진 환경별 분리 (와일드카드 금지)
- [ ] 모든 REST 엔드포인트 rate limit 적용
- [ ] 파일 경로 입력 검증 (Path traversal 방지)
- [ ] 인증/세션 보호 (TR-4 패턴)
- [ ] Secret은 env/secret manager에서만 로드
- [ ] 에러 메시지가 민감 정보 누출 안 함

---

## 3. Reliability & Performance

### 3.1 Backend SLOs (production)

| Metric | Target | Measured By |
|--------|--------|-------------|
| HTTP 5xx rate | < 0.5% | access log / Prometheus (Sprint 3에서) |
| p95 latency (REST) | < 200ms | 동일 |
| p99 latency (REST) | < 500ms | 동일 |
| WebSocket reconnect p95 | < 3s (with backoff) | 클라이언트 telemetry |
| Training loop RAM | < 2GB per env | `docker stats` |
| MongoDB query p95 | < 50ms | driver metrics |

### 3.2 Frontend Performance (Core Web Vitals)

| Metric | Target | Tool |
|--------|--------|------|
| LCP | < 2.5s | Lighthouse |
| INP | < 200ms | 동일 |
| CLS | < 0.1 | 동일 |
| Bundle (gzipped) | < 300kb (app page) | Vite build report |

### 3.3 Availability

| Metric | Target |
|--------|--------|
| Dev 환경 uptime | best-effort (개발 피드백 대기 수준) |
| QA 환경 uptime | ≥ 95% (검증 기간 내) |
| Prod 환경 uptime | ≥ 99% (월간) |
| 복구 drill 주기 | 최소 분기 1회 (MongoDB 백업 복구 검증) |

---

## 4. Delivery & Process

### 4.1 Sprint Metrics

| Metric | Target |
|--------|--------|
| Sprint 일정 준수율 | ≥ 80% (계획 대비 실제 완료 항목 비율) |
| dev 머지 후 health check 수행률 | 100% (예외 없음) |
| QA 검증 리포트 작성률 | 100% (모든 릴리스 후보) |
| 릴리스 시 main 머지 + 태그 수행률 | 100% |

### 4.2 Issue Hygiene

| Metric | Target |
|--------|--------|
| PR 오픈 → 리뷰 완료 | ≤ 1일 |
| CRITICAL 이슈 대응 | ≤ 1일 |
| HIGH 이슈 대응 | ≤ 3일 |
| 이슈 close 시 해결 커밋 링크 기록 | 100% |

### 4.3 Documentation Freshness

| Doc | 업데이트 트리거 |
|-----|-----------------|
| CHANGELOG.md | 매 릴리스 (Unreleased → 버전 섹션) |
| DEPLOYMENT-STATUS.md | 매 환경 배포 |
| 릴리스 노트 (`docs/releases/v{v}-{env}.md`) | 매 환경 배포 |
| README.md Status 라인 | 매 스프린트 시작/종료 |
| Sprint 추적 문서 | 매일 (진행 중 스프린트) |

---

## 5. RL-Specific Metrics

### 5.1 Training Quality

| Metric | Target | Notes |
|--------|--------|-------|
| L3 봇 상대 win_rate | ≥ 60% | 5M step 기준 |
| L5 봇 상대 win_rate | ≥ 40% | 5M step 기준 |
| Self-toss exploit 발생률 | 0% | anti-toss-loop 리워드 셰이핑 덕 |
| 평균 rally length | ≥ 5 hits | L3 이상 상대 시 |

### 5.2 Training Pipeline Reliability

| Metric | Target |
|--------|--------|
| Training 세션 SIGTERM 복구 성공률 | 100% (TR-4) |
| 병렬 env 크래시율 | < 1% per 1M steps |
| 체크포인트 저장 실패율 | 0% |

---

## 6. Measurement Tools & Dashboards

| Tool | Status | Where |
|------|--------|-------|
| pytest-cov | Active | CI |
| vitest coverage | Active | CI |
| bandit / npm audit | Planned → Sprint 1 (QA-4) | CI |
| Prometheus + Grafana | Planned → Sprint 3 (DO-1) | prod stack |
| Log aggregation | Planned (BE-3 구조화 로그 전제) | Sprint 3+ |
| Lighthouse CI | Not planned | — |

---

## 7. Gate Matrix — "이건 넘어야 릴리스"

| Gate | v0.2.1 | v0.2.2 | v0.3.0 | 비고 |
|------|--------|--------|--------|------|
| CRITICAL 보안 이슈 0건 | ✅ | ✅ | ✅ | 필수 |
| Backend coverage ≥ 80% | — | ✅ | ✅ | v0.2.2부터 |
| bandit/npm audit HIGH 0건 | ✅ | ✅ | ✅ | QA-4 도입 후 |
| CI 실패 없이 연속 성공 | ✅ | ✅ | ✅ | 필수 |
| QA 검증 PASS 리포트 | ✅ | ✅ | ✅ | 필수 |
| PM prod 배포 승인 | ✅ | ✅ | ✅ | 필수 |
| main 머지 + 태그 | ✅ | ✅ | ✅ | 필수 |

---

## 8. Review Cadence

- **매 스프린트 완료 시**: 이 문서의 gate matrix 업데이트, 달성/미달 항목 기록
- **분기 1회**: 전체 기준 재검토 — 목표 수치 조정, 새 메트릭 추가
- **CRITICAL 인시던트 후**: 관련 메트릭 추가 고려
