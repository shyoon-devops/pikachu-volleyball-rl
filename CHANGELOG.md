# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/),
and this project adheres to [Semantic Versioning](https://semver.org/).

## [Unreleased]

v0.2.3 이후 scope. Trainer PR #42 (TensorBoard + early stopping + reproducibility + grid search + curriculum learning) + Evaluator PR #44 (E1-E10 baseline comparator / batch eval / history / timeseries / Elo tracker) 후속 릴리스 후보.

## [0.2.3] - 2026-04-12 (v0.2.2 QA blocker 3 hotfix / dev HEAD 77b871dd)

v0.2.2 QA 재검증(`d14c0c68`)에서 확인된 2 CRITICAL + 1 품질 이슈 수정. v0.2.2 전 환경 배포 직전 긴급 번들로 대체. 태그는 dev HEAD (`77b871dd`) 기준.

### Fixed — QA blockers (Sprint 2 post-promote)
- **BE-6 WS broadcast hotfix** (`91c7233d`): `fix(ws): restore training:status broadcast after parallel fan-out` — `fb1f5e64` 의 `asyncio.gather` parallel fan-out 에서 `training:status` 가 일부 구독자에 도달하지 않던 회귀 복구. PM 의 live UI 관찰(Start 버튼 활성화 유지 + status badge "stopped") 해소. `backend/tests/test_training_status_broadcast.py` 회귀 스위트 신설
- **Net-collision vx reversal guards** (`bf6397cc`): `test(physics): harden net-collision vx reversal guards` — `b0d0aaee` faithful physics port 이후 공이 네트에 닿아도 vx 가 뒤집히지 않던 회귀 수정 + `test_engine.py::TestBallNetCollision` 가드 강화
- **Bot variance knobs** (`6af36c0c`): `fix(bot): add stochastic variance knobs to break repetitive play patterns` — L1~L5 전 레벨에 `jump_jitter` + `angle_variance` + `hesitation_rate` + `trajectory_noise_scale` 도입. L5 도 distinct skill edge 유지하면서 deterministic 플레이 제거

### Deployment
- **v0.2.2 was tagged but never deployed** — v0.2.3 이 v0.2.2 를 그대로 대체. env tag `v0.2.3-{dev,qa,prod}` 로 배포 진행
- **qa backend** (`:8002`) 복구 필요(#38) — v0.2.3 첫 배포 타이밍에 qa 재기동 동시 수행
- **prod** 는 v0.1.0 → v0.2.3 jump (BE-3/SEC-1-3/BUG-1-7/BE-1-7/FE-1-9 + v0.2.2 Sprint 2 + v0.2.3 hotfix 모두 최초 반영)

### Not in v0.2.3 (deferred)
- Trainer PR #42: reward 재훈련 검증 + TensorBoard + early stopping + reproducibility + grid search + curriculum learning
- Evaluator PR #44: E1-E10 baseline comparator, batch eval, history persistence, timeseries endpoint, Elo tracker

### Rollback
- target `v0.2.1` (`482df2d1`). prod 는 현재 v0.1.0-era 이므로 사실상 forward-only deploy

## [0.2.2] - 2026-04-12 (Sprint 2 complete / dev HEAD 121cb478)

Sprint 2 배치 — Backend 성능 3종(BE-5/6/7) + Frontend UX 4종(FE-6/7/8/9) + AI Engineer 의 gorisanson/pikachu-volleyball 원본 충실 포팅 + Designer D6-D10 + QA Sprint 1 회귀/재검증 스위트 + DevOps 모니터링 스택. 태그는 dev HEAD (`121cb478`) 기준. Trainer PR #42 는 v0.2.2 에 포함되지 않음 — v0.2.3 hotfix 로 이월.

### Added — Backend (performance & features)
- **BE-5 hot-path MongoDB indexes** (`ee7a6c0b`): startup 시 games / metrics / evaluations 컬렉션 인덱스 선언으로 조회 지연 저감
- **BE-6 parallel WS broadcast with serialize-once fan-out** (`fb1f5e64`): 메시지 1회 직렬화 후 클라이언트별 병렬 송출 — 다중 클라이언트 시 브로드캐스트 경로 최적화
- **BE-7 training metric persistence + time-bucket aggregation** (`027bc08e`): 학습 메트릭 MongoDB 영속화 + 시간-버킷 집계 조회

### Added — Frontend (UX)
- **FE-6 global ConnectionIndicator pill** (`265e3c30`): 앱 헤더에 WebSocket 연결 상태 전역 표시
- **FE-7 replay keyboard scrubbing** (`f10b6c25`): ←/→ 1프레임 단위, ↓/↑ 10프레임 단위 스텝 이동
- **FE-8 training Pause / Resume toggle** (`360fa1dd`): Stop 과 별개로 일시중지/재개 컨트롤 추가
- **FE-9 CheckpointList picker for model evaluation** (`668df41d`): Evaluation 패널에서 모델 체크포인트 리치 선택 UI

### Added — Design (D6-D10 polish)
- **D6-D10 training progress, chart tooltip, fullscreen, toast, error/skeleton** (`3cdef948`)
- **Chart semantics, arcade frame, button micro-anim, row states, mobile tab bar** (`9edec27b`)
- **Dev audit artifacts** (`08b86ead`)

### Changed — RL / Game engine (AI Engineer — 원본 충실도 복원)
- **Faithful port of game engine to gorisanson/pikachu-volleyball original** (`b0d0aaee`): 오리지널(1997) 물리 거동 충실 포팅
- **Gate ball-player collision with isCollisionWithBallHappened flag** (`e5d765a0`): 충돌 중복 방지 플래그 게이팅
- **Rebalance reward weights to prioritize winning over shaping** (`0f32235e`): 승리 기반 보상 가중치 상향, shaping 비중 하향
- **Remove duplicate Start button, unify training controls** (`9f050c87`)

### Added — Tests (QA & AI Engineer)
- **Physics regression suite pinning behavior to original source** (`ab0151cd`)
- **Rework tests affected by faithful physics port** (`47aa4ced`)
- **E2E, WS resilience, load, rate-limit, coverage report** (`a12c3117`)
- **16-bug regression suite + prod-20260412 QA report** (`720458bb`)
- **Sprint 1 fix verification suite — SEC-1/2/3, BUG-3/5, BE-1** (`d5aa9fce`)
- **Post-promotion QA re-verification script** (`057dc651`) + 확장 (`c3e2cc08`)
- **QA env verification report + dev-vs-QA diff** (`82f86187`, `c24764e5`)
- **Re-verify QA after redeploy — 6 fail / 35 pass, Sprint 1 fixes 랜딩 확인** (`d309a574`)
- **/api/health exemption probe + /live /ready split finding** (`243c6a14`)

### Fixed
- **Middleware: exempt metrics + health probes from rate limiter** (`38e29bdd`): `/api/metrics`, `/api/health*` 제외 — Prometheus / k8s 프로브 안정화
- **Double score display + canvas responsive scaling** (`ede4e347`, #27)
- **test_ws_resilience — 3 test bugs masked as server regressions** (`0a79eb44`): 테스트 버그 수정, BE-1 해당 없음으로 판정
- **/api/health rate-limit exemption test + 3 flakes** (`26e038b6`)

### Infrastructure (DevOps)
- **Loki + Promtail centralized log aggregation** (`f863c11e`)
- **CPU/GPU/memory/disk resources dashboard** (`fc44b70f`)
- **Backup/restore verification harness** (`da6a93c6`) — DO-3 선행 작업
- **promote.sh fix + smoke-test.sh for qa/prod verification** (`dac05c89`)
- **Prevent orphan containers + document two-server arch** (`79599088`)

### Docs
- **Retract BE-1 finding — root cause was my test bugs not server** (`2a11a0f4`)
- **Full-suite stability note + clarify isolated vs bundled pass rates** (`d981d05d`)
- **Notify Trainer of reward rebalance + rerun-training request** (`1a40c8fa`)

### Deployment
- **dev tag** — `121cb478` (v0.2.2 tag target)
- **qa/prod 배포** — DevOps 수행 대기 (env tag `v0.2.2-qa`, `v0.2.2-prod` 부착 필수)
- **prod → main 머지** — prod 승격 후 필수

### Not in v0.2.2 (deferred to v0.2.3)
- **Trainer PR #42**: reward rebalance 검증 + TensorBoard integration + early stopping + reproducibility + grid search + curriculum learning — dev 미머지

### Known gaps
- FE 중복 Start 버튼 제거(`9f050c87`) 이후 전 환경 재배포 필요 — 현재 qa/prod frontend 는 v0.2.1 pre-fix 번들 서빙 중
- qa backend 가시성 복구 (#38) 선행 후 v0.2.2 QA 검증 진행

## [0.2.1] - 2026-04-12 (QA 재배포 완료, prod 대기 / dev HEAD 482df2d1)

Sprint 1 완료분 + 팀 자발적 품질 보강 + BE-2/BE-3 조기 착수분. 최초 QA 승격 (`15f4a11`) 이후 BE-3 재작업과 BE-2 가 dev 에 추가 병합되어 QA 재승격(`1baa3e3b`) 수행. 태그는 dev HEAD (`482df2d1`) 기준.

### Added (post-first-QA-promotion batch — sprint-2 items advanced into v0.2.1)
- **BE-3 JSON structured logging + /health/live|ready split** (`f6e71e80`): JSON 구조화 로깅 + liveness/readiness 분리. 초기 `13e103f` BE-3 에 추가된 확장분
- **BE-2 API TTL cache + unified pagination envelope** (`482df2d1`) — Sprint 2 (#31) 에서 조기 진입. TTL 기반 API 캐시 + 통일된 페이지네이션 응답 래퍼

### Deployment (updated)
- **dev → qa 재승격 완료** (2026-04-12): qa 브랜치 `1baa3e3b` — BE-2/BE-3 추가 병합분 포함

### Added (late batch — post-Sprint 1 finalization, 2026-04-12 03:xx)
- **Prometheus metrics endpoint** (`5da6af3`): `/api/metrics` Prometheus exposition format — Sprint 3 DO-1 선행 작업
- **Dashboard loading skeleton** (`2a52a3c`): 초기 로드 시 스켈레톤 UI로 인지 지연 개선
- **Friendly error boundary** (`4697e6c`): retry/reload/home 옵션을 가진 global React error boundary
- **MongoDB connection pool + transient-error retry** (`79c1e34`): `build_mongo_client()` 풀/타임아웃 설정, `with_mongo_retry()` 지수 백오프; GameService/EvalService 랩. 11개 테스트 추가. env 오버라이드 지원 (MONGO_MAX_POOL_SIZE 등)
- **Dark/Light theme toggle** (`a3a332a`): OS prefers-color-scheme 동기화 + 수동 토글
- **WS Pydantic validation layer 통합** (`c90794c`): `WsEnvelope` + `WS_MESSAGE_SCHEMAS` 레지스트리, `parse_ws_message()` 센터. unknown_type 구조화 에러, client-initiated ping→pong, stable error `code` 필드. 13 + 4 테스트 추가
- **Replay speed controls 재정비** (`5057b56`): 0.5x/1x/2x/4x 버튼 a11y + 키보드 접근 강화
- **API endpoint error handling + structured logging** (`13e103f`) — **BE-3 충족**: `endpoint_guard` 데코레이터, 글로벌 unhandled-exception handler, 전 엔드포인트 구조화 로깅. list_games 서비스 미초기화 → 503, get_replay linked-game 실패 tolerance. 7 신규 테스트
- **Dashboard metrics chart 실시간 스무딩** (`26d7c5a`) — **FE-2 smoothing 부분 충족**: Recharts built-in 250ms ease-out tween, `usePrefersReducedMotion` 훅, reduced-motion 미디어 쿼리 지원. MetricsChart.test.tsx 4 케이스

### Closed Issues (late batch)
- **#32 BE-3 Structured Logging + Health Check Depth** — 13e103f + BUG-2 fix로 해소

### Deployment
- **dev → qa 승격 완료** (2026-04-12): qa 브랜치 `15f4a11` (`chore: promote dev to qa`) — DevOps `scripts/promote.sh dev-to-qa` 실행 결과

### Still Pending for v0.2.1
- Docker QA 환경 (:8002/:3001/:27019) 배포 검증
- QA Engineer 전체 검증 리포트
- prod 승인 → 승격 → main 머지 + `v0.2.1` 태그

### Infrastructure (v0.2.1 scope, 이전 섹션에서 누락)
- **Two-server architecture split** (`75fb4292`): Backend + MongoDB → GPU 서버 (192.168.0.250), Frontend → yoonbian-2 (192.168.0.248) nginx 정적 서빙. docker-compose 에서 `frontend` 서비스 제거, `frontend/nginx-{dev,qa,prod}.conf` 3종 + `scripts/deploy-frontend.sh` 추가. CORS_ORIGINS 환경별 갱신
- **WSL2 docker.exe 감지** (`2acaabb5`): 모든 deploy 스크립트 (`deploy-{dev,qa,prod}.sh`)에 WSL2 환경 docker 바이너리 경로 감지 로직 추가
- **Training 스레드 예외 로깅** (`52d2ee39`): 훈련 스레드 예외를 silent swallow 하지 않고 구조화 로그로 기록 — 과거 silent-failure 패턴 제거
- **테스트 파일 unused import 정리** (`a2c23296`)

### Added
- **QA-2 CI/CD Test Pipeline** (#25): GitHub Actions 테스트 파이프라인 + 커버리지 게이트 (9d257c9, PR #29)
- **QA-4 Security Auto-Scan** (#26): CI 보안 자동 스캔 (bandit, npm audit) (9d257c9, PR #29)
- **FE-3 GameCanvas Responsive** (#22): ResizeObserver 기반 반응형 캔버스 스케일링 (2338102)
- **FE-5 A11y Improvements** (#24): ARIA 라벨, 색상 대비, reduced-motion 지원 (2338102)
- **Monitoring/Backup**: Prometheus 메트릭 계측, 백업 스크립트, 디스크 정리 작업 (72e1606)
- **Expanded RL spaces**: Observation 12→18, Action 6→12, anti-toss-loop 리워드 셰이핑 (5a5def9, f8ea612)
- **QA Regression Suite**: 16-bug 회귀 테스트 + Sprint 1 수정 검증 스위트 (720458b, d5aa9fc)

### Fixed
- **BUG-1 WebSocket Queue Bounded** (#13): 큐 상한 + drop-oldest 정책으로 OOM 방지 (5d143ae, merged 8565887)
- **BUG-2 Health Check** (#14): MongoDB/disk/thread 실측 기반 health 응답 (5d143ae)
- **BUG-4 Heartbeat Pong** (#16): 완전한 ping/pong 프로토콜 (서버 + 클라이언트) (5d143ae)
- **BUG-6 Game Result Save** (#18): retry + fallback 영속화로 데이터 손실 방지 (5d143ae)
- **BUG-7 FE WS Reconnection** (#19): 지수 백오프 재연결 구현 (2338102)
- **Design Review — Sprite Rendering** (#27): 스코어 중복 표시 + 캔버스 반응형 스케일링 수정 (ede4e34)
- Dockerfile 복구 및 빌드 실패 해결 (167bc07)

### Changed
- 미머지 브랜치 3개(devops/trainer/evaluator)를 dev로 일괄 통합 (#3) — PR #28, PR #29 포함

### Closed Issues
#13, #14, #16, #18, #19, #22, #24, #25, #26, #27, #3 (11건)

### Known Issues
- v0.2.1은 dev 코드 완료 상태. QA 환경 배포 후 검증 필요 (#6의 연장선).
- v0.2.0도 QA 태그만 되어 있고 prod 미승격 — v0.2.1과 함께 prod 승격 여부 PM 판단 필요.

## [0.2.0] - 2026-04-11 (QA 환경 배포 완료, prod 미배포)

QA 환경(`:8002`) 태그 완료 — prod 승격 대기 중. 전체 릴리스 노트: [docs/releases/v0.2.0-qa.md](docs/releases/v0.2.0-qa.md).

### Security (CRITICAL)
- **SEC-1**: `/api/evaluation/run` path traversal 차단 — `Path.resolve()` + `MODEL_DIR` 경계 검증 (#9, 10c9f1d)
- **SEC-2**: CORS 와일드카드 `*` 제거, 환경별 허용 오리진 화이트리스트 적용 (#10, 10c9f1d)
- **SEC-3**: REST API 엔드포인트 rate limiting 적용 (#11, 10c9f1d)

### Added
- **TR-4 Training Session Protection (BLOCKER)**: SIGTERM 복구, 세이프 큐 enqueue, 세션 중복 보호 (PR #28, 6e8ea3e / #12)
- **BE-1 WebSocket Heartbeat + Backpressure**: ping/pong 프로토콜, 큐 상한, 슬로우 컨슈머 감지 (#20, 3f8abb8)
- **BE-4 Input Validation + Rate Limiting**: 요청 스키마 검증 강화, 엔드포인트별 레이트 리밋 (#21, 3f8abb8)
- **FE-1 Replay Keyboard Shortcuts**: 재생/일시정지(Space), 시크(←/→), 배속(↑/↓) (#23, 830278b)
- **Evaluator**: 크로스 환경 평가 리포트 및 기준 문서화 (294f524)
- **Game Visuals**: 오리지널 피카추 배구 비주얼 포팅 — 구름, 파도, 공 이펙트, 스코어 스프라이트 (f25e50d)
- **Designer**: 하드코딩 값 토큰화, WCAG 명도 대비 위반 해소 (e19bc33)

### Fixed
- **BUG-3**: WebSocket 중복 start 크래시 가드, training_status 완전 데이터 반환 (#15, 5c30671)
- **BUG-5**: `/api/models`·`/api/replays` 필드 불일치 및 replay ID 라우팅 수정 (#17, 07c36bd)
- FE 페이로드 래핑 수정, `game_id` 추가, replay 응답 강화 (ac03e02)
- 누락된 반응형 브레이크포인트 4개 컴포넌트 복구 (18bfc32)
- Observation space shape 문서 정정 (19 → 18 features) + space spec 섹션 추가 (541f15a, 3823ecc)

### Changed
- **Designer**: CSS를 TSX에서 분리하여 .css 파일로 독립 관리
- **Frontend Engineer**: 모든 인라인 스타일을 className + CSS 파일로 변환
- **DevOps Engineer**: CI/CD 파이프라인 강화 — 커버리지 리포트, CD 워크플로우, 셀프호스트 러너

### Known Issues (prod 승격 전 해결 필요)
- 잔여 HIGH 버그 5건 (BUG-1/2/4/6/7) — Sprint 1 범위 내 처리 중
- prod 배포 후 main 브랜치 머지 + v0.2.0 태그 필요 (릴리스 워크플로우 업데이트: [docs/WORKFLOW.md](docs/WORKFLOW.md))

## [0.1.0] - 2026-04-11

Initial release — 전체 시스템 MVP 완성.

### Added

#### Game Engine (AI Engineer)
- 물리 기반 2D 피카추 배구 엔진 (`backend/game/engine.py`)
  - 충돌 감지 (공-플레이어, 공-네트, 공-경계)
  - 중력, 점프, 다이브, 파워 히트 메커닉
  - 득점 시스템 (15점 선승)
- 게임 상수 정의 (`backend/game/constants.py`)
- Rule-based Bot 5단계 난이도 (`backend/game/bot.py`)
  - L1(초보) ~ L5(완벽): reaction_delay, prediction_error, miss_probability 차등
- Gymnasium 호환 RL 환경 (`backend/rl/env.py`)
  - Observation: 12차원 정규화 벡터
  - Action: 6개 이산 행동 (noop, left, right, jump, left+jump, right+jump)
  - Reward shaping: 득점(+10), 실점(-10), 승리(+20), 패배(-20), 랠리(+0.5)

#### Training Pipeline (Trainer)
- PPO 훈련 매니저 (`backend/rl/trainer.py`)
  - 백그라운드 스레드 기반 훈련 (start/stop/resume)
  - 커리큘럼 러닝 — 봇 난이도 동적 조정
  - 8개 병렬 환경 (SubprocVecEnv)
  - 기본 하이퍼파라미터: lr=3e-4, n_steps=2048, batch=64, epochs=10
- 콜백 시스템 (`backend/rl/callbacks.py`)
  - MetricsCallback: 주기적 reward/loss/win_rate 수집
  - CheckpointCallback: 모델 체크포인트 자동 저장
  - LiveFrameCallback: 실시간 게임 프레임 캡처

#### Evaluation System (Evaluator)
- 모델 평가 시스템 (`backend/rl/evaluator.py`)
  - evaluate(): N게임 실행 후 win_rate, avg_score, avg_rally_length 산출
  - compare_checkpoints(): 여러 체크포인트 비교 평가

#### Backend API (Backend Engineer)
- FastAPI REST API (`backend/app/api/routes.py`)
  - GET /api/health, /api/training/status
  - GET /api/games (페이지네이션), /api/games/{id}
  - GET /api/replays/{game_id}, /api/models
  - POST /api/evaluation/run, GET /api/evaluation/results
- WebSocket 실시간 통신 (`backend/app/ws/`)
  - training:start/stop/resume, training:set_level
  - training:metrics, training:frame, game:result 스트리밍
- MongoDB 연동 (motor async driver)
  - Collections: games, metrics, evaluations
- 서비스 계층 (`backend/app/services/`)
  - TrainingService, EvalService, GameService, ReplayService
- Replay 저장 (msgpack 직렬화, 최근 1000개 유지)

#### Frontend (Frontend Engineer)
- React 19 + TypeScript + Vite 8 프로젝트 초기화
- Dashboard 페이지 (`/`)
  - TrainingControls: 훈련 시작/중지/재개, 봇 레벨 셀렉터
  - HyperparamForm: 하이퍼파라미터 입력 폼
  - MetricsChart: Recharts 기반 reward/win_rate/loss 차트
  - GameCanvas: PixiJS 기반 실시간 게임 렌더링 (30fps→60fps 보간)
- Replay 페이지 (`/replay/:id`)
  - ReplayPlayer: 리플레이 재생/일시정지/배속/시크
  - ReplayList: 리플레이 목록
- Evaluation 페이지 (`/evaluation`)
  - EvalPanel: 평가 트리거 + 결과 테이블
  - EvalChart: 모델 비교 차트
- Hooks: useWebSocket (자동 재연결), useTrainingState
- API 클라이언트 (`frontend/src/lib/api.ts`)

#### Design System (Designer)
- Arcade-themed dark mode 디자인 시스템
- CSS custom properties 기반 디자인 토큰 (`frontend/src/styles/tokens.css`)
- 글로벌 스타일 (`frontend/src/styles/global.css`)
- 컴포넌트별 CSS 파일 (Dashboard, Controls, Metrics, Replay, Evaluation)

#### DevOps (DevOps Engineer)
- Docker 컨테이너화
  - Backend Dockerfile (Python 3.11, multi-stage)
  - Frontend Dockerfile (Node build → Nginx)
  - .dockerignore
- Docker Compose 설정
  - `docker-compose.yml` — Production 환경 (:8000/:5173/:27017)
  - `docker-compose.dev.yml` — Development 환경 (:8001/:3000/:27018)
  - `docker-compose.qa.yml` — QA 환경 (:8002/:3001/:27019)
- CI/CD (`/.github/workflows/ci.yml`)
  - Python lint + test, Frontend lint + build
- 운영 스크립트
  - `scripts/deploy-{dev,qa,prod}.sh` — 환경별 배포
  - `scripts/promote.sh` — 환경 간 승격 (dev→qa→prod)
  - `scripts/release.sh` — 릴리스 (버전, 태그, 체인지로그)
  - `scripts/setup.sh` — 초기 설정
  - `scripts/cleanup-replays.sh` — 리플레이 정리
  - `scripts/status.sh` — 환경 상태 확인
- 환경별 .env 파일 (.env.dev, .env.qa, .env.prod, .env.example)
- .gitignore 설정

#### Test Suite (QA Engineer)
- Backend 테스트 (`backend/tests/`)
  - test_engine.py — 게임 엔진 유닛 테스트
  - test_bot.py — 봇 행동 테스트
  - test_env.py — RL 환경 테스트
  - test_trainer.py — 훈련 파이프라인 테스트
  - test_evaluator.py — 평가 시스템 테스트
  - test_api.py — REST API 엔드포인트 테스트
  - test_ws.py — WebSocket 핸들러 테스트
  - test_integration.py — 서비스 간 통합 테스트
  - test_game_scenarios.py — 게임 시나리오 테스트 (득점, 충돌, 랠리)
  - test_coverage_gaps.py — 커버리지 갭 보완 테스트
- Frontend 테스트
  - TrainingControls.test.tsx, GameOverlay.test.tsx
  - ReplayControls.test.tsx, useWebSocket.test.ts

[Unreleased]: https://github.com/shyoon-devops/pikachu-volleyball-rl/compare/v0.2.1...HEAD
[0.2.1]: https://github.com/shyoon-devops/pikachu-volleyball-rl/compare/v0.2.0...v0.2.1
[0.2.0]: https://github.com/shyoon-devops/pikachu-volleyball-rl/releases/tag/v0.2.0
[0.1.0]: https://github.com/shyoon-devops/pikachu-volleyball-rl/releases/tag/v0.1.0
