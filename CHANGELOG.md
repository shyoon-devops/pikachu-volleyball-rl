# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/),
and this project adheres to [Semantic Versioning](https://semver.org/).

## [Unreleased]

Sprint 1 (v0.2.1) 작업 진행 중 — 추적 문서: [docs/sprint-tracking/sprint1-v0.2.1.md](docs/sprint-tracking/sprint1-v0.2.1.md)

### In Progress
- FE-3: GameCanvas Responsive Scaling (#22)
- FE-5: A11y Improvements (#24)
- QA-2: CI/CD Test Pipeline (#25), QA-4: Security Auto-Scan in CI (#26)
- BUG-1/2/4/6/7: 잔여 HIGH 버그 수정

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

[Unreleased]: https://github.com/shyoon-devops/pikachu-volleyball-rl/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/shyoon-devops/pikachu-volleyball-rl/releases/tag/v0.2.0
[0.1.0]: https://github.com/shyoon-devops/pikachu-volleyball-rl/releases/tag/v0.1.0
