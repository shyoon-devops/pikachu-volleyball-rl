# Changelog

All notable changes to this project will be documented in this file.
Format based on [Keep a Changelog](https://keepachangelog.com/), adheres to [Semantic Versioning](https://semver.org/).

## [0.2.0] - 2026-04-12

First feature-complete release. 전체 시스템 통합 완료.

### Added

#### Game Engine (AI Engineer)
- 물리 기반 2D 피카추 배구 엔진 — 충돌, 중력, 네트, 득점 (`backend/game/engine.py`)
- Rule-based Bot 5단계 난이도 L1~L5 (`backend/game/bot.py`)
- Gymnasium 호환 RL 환경 — obs 12D, action Discrete(6) (`backend/rl/env.py`)
- 오리지널 피카추 배구 스프라이트 시트 및 사운드 에셋

#### RL Training (Trainer)
- PPO 훈련 매니저 — start/stop/resume, 커리큘럼 러닝 (`backend/rl/trainer.py`)
- 콜백 시스템 — MetricsCallback, CheckpointCallback, LiveFrameCallback (`backend/rl/callbacks.py`)
- 8개 병렬 환경 SubprocVecEnv

#### RL Evaluation (Evaluator)
- 모델 평가 시스템 — win_rate, avg_score, avg_rally_length (`backend/rl/evaluator.py`)
- 체크포인트 비교 평가 (`compare_checkpoints`)

#### Backend API (Backend Engineer)
- FastAPI REST API — health, training, games, replays, models, evaluation (`backend/app/`)
- WebSocket 실시간 통신 — metrics, live frames, game results (`backend/app/ws/`)
- MongoDB 연동 (motor async) — games, metrics, evaluations collections
- Replay 저장 (msgpack 직렬화)

#### Frontend (Frontend Engineer)
- React 19 + TypeScript + Vite 8 대시보드
- PixiJS 기반 실시간 게임 렌더링 (30fps→60fps 보간)
- Recharts 메트릭 차트 (reward, win_rate, loss)
- 리플레이 재생기 (재생/일시정지/배속/시크)
- 모델 평가 패널 및 비교 차트
- WebSocket hooks (자동 재연결)

#### Design System (Designer)
- Arcade-themed dark mode 디자인 시스템
- CSS custom properties 기반 디자인 토큰 (`frontend/src/styles/tokens.css`)
- 컴포넌트별 CSS 파일 분리

#### Infrastructure (DevOps Engineer)
- Docker 컨테이너화 — Backend (Python 3.11) + Frontend (Nginx)
- 3-환경 Docker Compose — dev(:8001/:3000), qa(:8002/:3001), prod(:8000/:5173)
- GitHub Actions CI — lint + test (Python, TypeScript)
- CD 워크플로우 및 셀프호스트 러너 지원
- 운영 스크립트 — deploy, promote, release, status, cleanup

#### Testing (QA Engineer)
- Backend 테스트 10개 모듈 — engine, bot, env, trainer, evaluator, API, WS, integration, scenarios, coverage gaps
- Frontend 테스트 4개 — TrainingControls, GameOverlay, ReplayControls, useWebSocket

### Fixed
- Backend: 잘못된 ObjectId 및 누락된 모델 파일 예외 처리 (`dbdb826`)
- Backend: 중복 training:start로 인한 WebSocket 크래시 방지 (`5c30671`)
- Backend: 리플레이 목록 API 추가, 프레임 직렬화 완성, 레거시 리플레이 백필 (`52dfd43`)
- Frontend: conflict markers 해결 (`41f4fdb`)
- AI: 보상 쉐이핑 개선 — PPO 수렴 속도 향상 (`46e9aa5`)

### Changed
- Frontend: 모든 인라인 스타일을 className + CSS 파일로 변환 (`f171ada`)
- Frontend: CSS를 TSX에서 분리 — Designer가 .css 파일만 관리 (`e21eb99`)
- Designer: CSS 셀렉터를 FE className 규칙에 맞춤 정렬 (`212c081`)
- Designer: 반응형 브레이크포인트 및 요소 레벨 셀렉터 개선 (`4d93664`)
- CI/CD: 커버리지 리포트, CD 워크플로우, 셀프호스트 러너 추가 (`48d6726`)

## [0.1.0] - 2026-04-11

### Added
- 프로젝트 초기 구조 생성
- 팀별 프롬프트 및 기획 문서

[0.2.0]: https://github.com/shyoon-devops/pikachu-volleyball-rl/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/shyoon-devops/pikachu-volleyball-rl/releases/tag/v0.1.0
