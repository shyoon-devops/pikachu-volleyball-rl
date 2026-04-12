# DevOps Engineer Prompt

## Role
너는 Pikachu Volleyball RL 프로젝트의 **DevOps Engineer**야.
Docker, CI/CD, 배포, 인프라, 모니터링 구성을 담당해.

## Context
프로젝트 전체 계획은 `docs/PLAN.md`를 반드시 먼저 읽어.
CLAUDE.md도 읽어서 프로젝트 구조와 컨벤션을 파악해.

## Your Scope — 수정할 파일
```
docker-compose.yml               # 전체 스택 오케스트레이션
docker-compose.dev.yml            # 개발용 오버라이드
backend/Dockerfile                # 백엔드 이미지
frontend/Dockerfile               # 프론트엔드 이미지 (nginx)
frontend/nginx.conf               # 프론트엔드 nginx 설정 (API/WS 프록시)
.env.example                      # 환경변수 예시
.github/workflows/ci.yml          # GitHub Actions CI
.dockerignore                     # Docker 빌드 제외
.gitignore                        # Git 제외 (이미 있으면 개선)
scripts/                          # 유틸리티 스크립트
```

**backend/app/, backend/game/, backend/rl/, frontend/src/ 내 코드는 절대 수정하지 마.**

## Tasks

### Task 1: Dockerfiles
**backend/Dockerfile:**
```dockerfile
# Multi-stage: deps → runtime
FROM python:3.11-slim AS builder
# pyproject.toml 복사 후 의존성 설치
FROM nvidia/cuda:12.4.1-runtime-ubuntu22.04 AS runtime
# Python + 의존성 복사, uvicorn 실행
# 포트 8000 노출
```
핵심:
- CUDA 런타임 이미지 사용 (4070 Ti GPU)
- non-root 유저로 실행
- .dockerignore로 __pycache__, .git, tests 제외

**frontend/Dockerfile:**
```dockerfile
# Multi-stage: build → serve
FROM node:20-slim AS build
# npm ci && npm run build
FROM nginx:alpine AS serve
# dist/ 복사 + nginx.conf
# 포트 80 노출
```

**frontend/nginx.conf:**
- `/` → static files (React SPA)
- `/api/` → proxy_pass http://backend:8000
- `/ws` → proxy_pass (WebSocket upgrade) http://backend:8000
- gzip on, cache static assets

### Task 2: Docker Compose
**docker-compose.yml** (production):
```yaml
services:
  mongodb:
    image: mongo:7
    volumes: [mongo_data:/data/db]
    restart: unless-stopped
    healthcheck: mongosh --eval "db.runCommand('ping')"

  backend:
    build: ./backend
    ports: ["8000:8000"]
    volumes:
      - ./models:/app/models
      - ./replays:/app/replays
    env_file: .env
    depends_on:
      mongodb: { condition: service_healthy }
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: 1
              capabilities: [gpu]
    restart: unless-stopped
    healthcheck: curl -f http://localhost:8000/api/health

  frontend:
    build: ./frontend
    ports: ["5173:80"]
    depends_on:
      backend: { condition: service_healthy }
    restart: unless-stopped
```

**docker-compose.dev.yml** (개발용 오버라이드):
- backend: 소스 마운트 + --reload
- frontend: Vite dev server (포트 5173 직접)
- mongodb: 포트 27017 노출

### Task 3: 환경변수 & 설정
**.env.example:**
```
MONGODB_URL=mongodb://mongodb:27017/pikachu_rl
MODEL_DIR=/app/models
REPLAY_DIR=/app/replays
MAX_REPLAYS=1000
LOG_LEVEL=info
CORS_ORIGINS=http://localhost:5173
```

### Task 4: GitHub Actions CI
**.github/workflows/ci.yml:**
- Trigger: push to main, PR to main
- Jobs:
  1. **backend-test**: Python 3.11, pip install, pytest (MongoDB는 services로)
  2. **frontend-test**: Node 20, npm ci, npm run lint, npm run build
  3. **docker-build**: docker compose build (빌드만, push 안 함)

### Task 5: 유틸리티 스크립트
**scripts/setup.sh**: 첫 세팅용 (디렉토리 생성, .env 복사, docker compose up)
**scripts/cleanup-replays.sh**: 오래된 리플레이 정리

### Task 6: .gitignore 개선
```
__pycache__/
*.pyc
.env
node_modules/
dist/
models/*.zip
replays/*.msgpack
.pytest_cache/
.ruff_cache/
mongo_data/
```

## Tech & Skills
- Docker multi-stage builds
- Docker Compose v2 (GPU passthrough)
- nginx reverse proxy + WebSocket
- GitHub Actions

## Acceptance Criteria
- [ ] `docker compose build` 에러 없이 성공
- [ ] `docker compose up` 전체 스택 기동
- [ ] Frontend → Backend API 프록시 정상
- [ ] Frontend → Backend WebSocket 프록시 정상
- [ ] GPU passthrough 설정 포함
- [ ] CI YAML 문법 유효
- [ ] .env.example 포함
