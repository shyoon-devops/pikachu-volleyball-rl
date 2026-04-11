# Pikachu Volleyball RL

2D 피카추 배구 게임에 강화학습(PPO)을 적용하여 AI를 훈련하고, 웹 대시보드에서 실시간으로 훈련 과정을 모니터링하는 프로젝트입니다.

## Architecture

```
┌──────────────────────────────────────────────────────────────┐
│                        Frontend (React)                       │
│  ┌─────────────┐  ┌──────────────┐  ┌──────────────────────┐ │
│  │  Dashboard   │  │ Replay Player│  │  Evaluation Panel    │ │
│  │  - Controls  │  │ - Playback   │  │  - Model Comparison  │ │
│  │  - Metrics   │  │ - Seek       │  │  - Win Rate Charts   │ │
│  │  - Live Game │  │ - Speed      │  │  - Eval Trigger      │ │
│  └──────┬───────┘  └──────┬───────┘  └──────────┬───────────┘ │
│         │ WebSocket        │ REST API            │ REST API    │
└─────────┼──────────────────┼─────────────────────┼────────────┘
          │                  │                     │
┌─────────┴──────────────────┴─────────────────────┴────────────┐
│                     Backend (FastAPI)                          │
│  ┌───────────────┐  ┌────────────────┐  ┌──────────────────┐  │
│  │  WebSocket     │  │  REST API       │  │  Services        │  │
│  │  - Metrics     │  │  - /api/games   │  │  - Training      │  │
│  │  - Live Frames │  │  - /api/models  │  │  - Evaluation    │  │
│  │  - Game Result │  │  - /api/replays │  │  - Replay        │  │
│  └───────┬────────┘  └───────┬─────────┘  └───────┬──────────┘  │
│          │                   │                     │             │
│  ┌───────┴───────────────────┴─────────────────────┴──────────┐  │
│  │                    Game Engine (Pure Python)                │  │
│  │  ┌──────────┐  ┌─────────────┐  ┌────────────────────────┐│  │
│  │  │ Physics  │  │ Rule-based  │  │  Gymnasium RL Env      ││  │
│  │  │ Engine   │  │ Bot (L1-L5) │  │  (Obs: 12D, Act: 6)   ││  │
│  │  └──────────┘  └─────────────┘  └────────────────────────┘│  │
│  └────────────────────────────────────────────────────────────┘  │
└──────────────────────────────────┬────────────────────────────────┘
                                   │
                    ┌──────────────┴──────────────┐
                    │         MongoDB              │
                    │  - games, metrics, evals     │
                    └─────────────────────────────┘
```

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | Python 3.11+ / FastAPI / Uvicorn |
| RL Framework | Stable-Baselines3 (PPO) / Gymnasium |
| Frontend | React 19 + TypeScript + PixiJS 8 + Vite 8 |
| Charts | Recharts |
| Real-time | WebSocket (native) |
| Database | MongoDB 7 (motor async driver) |
| Serialization | msgpack (replays), JSON (API) |
| GPU | NVIDIA GPU (CUDA) |
| Deploy | Docker Compose (multi-environment) |
| CI/CD | GitHub Actions |
| Testing | pytest (backend) / Vitest (frontend) |

## Prerequisites

- Docker & Docker Compose v2
- NVIDIA GPU + NVIDIA Container Toolkit (for RL training)
- Node.js 20+ (frontend 로컬 개발 시)
- Python 3.11+ (backend 로컬 개발 시)

## Quick Start

### Docker Compose (권장)

```bash
# 레포 클론
git clone https://github.com/shyoon-devops/pikachu-volleyball-rl.git
cd pikachu-volleyball-rl

# 환경 변수 설정
cp .env.example .env

# 전체 스택 실행
docker compose up --build
```

접속:
- Frontend: http://localhost:5173
- Backend API: http://localhost:8000
- API Docs: http://localhost:8000/docs

### Multi-Environment

| Environment | Command | Backend | Frontend | MongoDB |
|-------------|---------|---------|----------|---------|
| **dev** | `docker compose -f docker-compose.dev.yml up` | :8001 | :3000 | :27018 |
| **qa** | `docker compose -f docker-compose.qa.yml up` | :8002 | :3001 | :27019 |
| **prod** | `docker compose up` | :8000 | :5173 | :27017 |

### Local Development

**Backend:**
```bash
cd backend
pip install -e ".[dev]"
uvicorn app.main:app --reload --port 8000
```

**Frontend:**
```bash
cd frontend
npm install
npm run dev
```

**MongoDB (Docker):**
```bash
docker compose up mongodb
```

## Project Structure

```
pikachu-volleyball-rl/
├── backend/
│   ├── game/              # Game engine (순수 Python, I/O 없음)
│   │   ├── constants.py   # 게임 상수 (코트, 물리, 점수)
│   │   ├── engine.py      # 물리 엔진 + 충돌 + 득점
│   │   └── bot.py         # Rule-based bot (L1~L5 난이도)
│   ├── rl/                # RL 환경 + 훈련
│   │   ├── env.py         # Gymnasium 환경 (obs: 12D, act: 6)
│   │   ├── trainer.py     # PPO 훈련 매니저 (SB3)
│   │   ├── evaluator.py   # 모델 평가 시스템
│   │   └── callbacks.py   # Metrics, Checkpoint, LiveFrame 콜백
│   ├── app/               # FastAPI 서버
│   │   ├── api/routes.py  # REST endpoints
│   │   ├── ws/            # WebSocket handlers + manager
│   │   ├── models/        # MongoDB document schemas
│   │   └── services/      # Business logic (training, eval, replay)
│   └── tests/             # 테스트 (unit, integration, scenario)
├── frontend/
│   └── src/
│       ├── components/
│       │   ├── dashboard/  # 훈련 대시보드 (Controls, Metrics, HyperparamForm)
│       │   ├── game/       # PixiJS 게임 캔버스 + 오버레이
│       │   ├── replay/     # 리플레이 재생 (Player, Controls, List)
│       │   └── evaluation/ # 모델 평가 패널 (EvalPanel, EvalChart)
│       ├── hooks/          # useWebSocket, useTrainingState
│       ├── lib/            # API client, types
│       └── styles/         # Design tokens, global CSS
├── scripts/               # 배포/운영 스크립트
│   ├── deploy-{dev,qa,prod}.sh
│   ├── promote.sh         # 환경 간 승격 (dev→qa→prod)
│   ├── release.sh         # 릴리스 (버전, 태그, 체인지로그)
│   └── status.sh          # 환경 상태 확인
├── docker-compose.yml         # Production 환경
├── docker-compose.dev.yml     # Development 환경
├── docker-compose.qa.yml      # QA 환경
├── docs/
│   ├── PLAN.md            # 기능 명세서
│   └── WORKFLOW.md        # 개발/배포 워크플로우
├── CHANGELOG.md
└── VERSION
```

## Key Features

### Game Engine
- 물리 기반 2D 피카추 배구 엔진 (충돌, 중력, 네트)
- 5단계 난이도의 Rule-based Bot (L1: 초보 ~ L5: 완벽)
- Gymnasium 호환 RL 환경 (12차원 관측, 6개 액션)

### RL Training
- PPO (Proximal Policy Optimization) via Stable-Baselines3
- 커리큘럼 러닝: 봇 난이도를 점진적으로 상향
- 8개 병렬 환경 (SubprocVecEnv)
- 실시간 메트릭 스트리밍 (reward, win_rate, loss)

### Web Dashboard
- 실시간 훈련 제어 (시작/중지/재개/봇 레벨 조정)
- PixiJS 기반 라이브 게임 시각화 (30fps → 60fps 보간)
- 메트릭 차트 (Recharts: reward, win_rate, loss 추이)
- 리플레이 재생 (재생/일시정지/배속/시크)
- 모델 평가 및 버전 비교

### API
- REST: 게임 히스토리, 모델 목록, 평가 결과
- WebSocket: 실시간 훈련 메트릭, 라이브 프레임, 게임 결과

## Testing

```bash
# Backend 테스트
cd backend
pytest tests/ -v --cov

# Frontend 테스트
cd frontend
npm run test
```

테스트 범위:
- **Unit**: 게임 엔진, 봇, RL 환경, 훈련 파이프라인, 평가
- **Integration**: API 엔드포인트, WebSocket, 서비스 계층
- **Scenario**: 게임 시나리오 (득점, 충돌, 경계, 랠리)
- **Frontend**: 컴포넌트, hooks, 상호작용

## Deployment

### Release Process

```bash
# 1. dev → qa 승격
scripts/promote.sh dev-to-qa

# 2. QA 테스트 통과 후 qa → prod 승격
scripts/promote.sh qa-to-prod

# 3. 릴리스 (버전 태깅 + CHANGELOG 업데이트)
scripts/release.sh 0.2.0
```

### Environment Status

```bash
scripts/status.sh
```

## Team

| Role | Scope |
|------|-------|
| AI Engineer | Game engine, Bot, RL environment |
| Trainer | PPO training pipeline, callbacks |
| Evaluator | Model evaluation, comparison |
| Backend Engineer | FastAPI, WebSocket, MongoDB |
| Frontend Engineer | React components, hooks, API client |
| Designer | CSS design system, arcade UI theme |
| DevOps Engineer | Docker, CI/CD, multi-env deployment |
| QA Engineer | Test suite (unit, integration, scenario) |
| Product Manager | Version, docs, release, GitHub management |

## Version

Current: **0.1.0** — See [CHANGELOG.md](CHANGELOG.md) for details.

## License

This project is for educational and research purposes.
