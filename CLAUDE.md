# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Pikachu Volleyball RL — 2D 피카추 배구 게임 + 강화학습(PPO) 훈련 + 웹 대시보드 모니터링 프로젝트.

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | Python 3.11+ / FastAPI / Uvicorn |
| RL | Stable-Baselines3 (PPO) / Gymnasium |
| Frontend | React 18 + TypeScript + PixiJS + Vite |
| Real-time | WebSocket (native) |
| Database | MongoDB (motor async driver) |
| Serialization | msgpack (replays), JSON (API) |
| GPU | NVIDIA 4070 Ti (CUDA) |
| Deploy | Docker Compose (single server) |

## Project Structure

```
├── backend/
│   ├── game/          # 게임 엔진 (constants, engine, bot) — 순수 Python, I/O 없음
│   ├── rl/            # RL 환경, 훈련, 평가 — SB3/Gymnasium
│   ├── app/           # FastAPI 서버
│   │   ├── api/       # REST endpoints
│   │   ├── ws/        # WebSocket handlers
│   │   ├── models/    # MongoDB document schemas
│   │   └── services/  # Business logic
│   └── tests/         # pytest
├── frontend/src/
│   ├── components/    # game/, dashboard/, replay/, evaluation/
│   ├── hooks/         # useWebSocket, useTrainingState
│   └── lib/           # api client, types
├── models/            # 모델 체크포인트 (.zip)
├── replays/           # 리플레이 데이터 (.msgpack)
└── docs/              # 계획서, 팀 프롬프트
```

## Common Commands

### Backend
```bash
cd backend
pip install -e ".[dev]"         # Install with dev deps
pytest tests/ -v                # Run all tests
pytest tests/test_engine.py -v  # Run specific test file
ruff check .                    # Lint
ruff format .                   # Format
uvicorn app.main:app --reload   # Dev server on :8000
```

### Frontend
```bash
cd frontend
npm install                     # Install deps
npm run dev                     # Dev server on :5173
npm run build                   # Production build
npm run lint                    # ESLint
npm run test                    # Vitest
```

### Docker
```bash
docker compose up --build       # Full stack
docker compose up mongodb       # MongoDB only (for local dev)
```

## Architecture Notes

- **Game engine** (`backend/game/`) is pure Python with zero I/O dependencies. It is used directly by the RL environment and can run headless at high speed.
- **RL training** runs in a background thread managed by `TrainingManager`. It communicates with the FastAPI server via `asyncio.Queue` for metrics and frame data.
- **WebSocket** is the single real-time channel. Message types are namespaced (e.g., `training:metrics`, `training:frame`, `game:result`).
- **Replay data** is stored as msgpack files on the filesystem. Game results and metrics go to MongoDB.
- **Frontend** renders game state via PixiJS, interpolating between server frames (30fps) to display at 60fps.

## Conventions

- Python: type hints everywhere, ruff for lint+format, pytest for tests
- TypeScript: strict mode, ESLint + Prettier
- Commits: conventional commits (`feat:`, `fix:`, `refactor:`, etc.)
- Branch per team member: `feat/{role}-{feature}`
