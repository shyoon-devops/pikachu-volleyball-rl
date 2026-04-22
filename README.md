<p align="center">
  <img src="docs/assets/banner.svg" alt="Pikachu Volleyball RL" width="600">
</p>

<h1 align="center">Pikachu Volleyball RL</h1>

<p align="center">
  <strong>2D 피카추 배구 + 강화학습(PPO) 훈련 + 실시간 웹 대시보드</strong>
</p>

<p align="center">
  <a href="https://github.com/shyoon-devops/pikachu-volleyball-rl/actions"><img src="https://github.com/shyoon-devops/pikachu-volleyball-rl/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <img src="https://img.shields.io/badge/version-2.0.0-blue" alt="Version">
  <img src="https://img.shields.io/badge/python-3.11+-3776AB?logo=python&logoColor=white" alt="Python">
  <img src="https://img.shields.io/badge/react-19-61DAFB?logo=react&logoColor=white" alt="React">
  <img src="https://img.shields.io/badge/SB3-PPO-FF6F00" alt="Stable-Baselines3">
  <img src="https://img.shields.io/badge/license-educational-green" alt="License">
</p>

<p align="center">
  <a href="#quick-start">Quick Start</a> &bull;
  <a href="#architecture">Architecture</a> &bull;
  <a href="#key-features">Features</a> &bull;
  <a href="CHANGELOG.md">Changelog</a> &bull;
  <a href="docs/PLAN.md">Spec</a>
</p>

---

PPO 에이전트가 Rule-based Bot(L1~L5)을 상대로 피카추 배구를 학습합니다. 웹 대시보드에서 훈련을 제어하고, 실시간 게임과 메트릭을 관찰하며, 리플레이를 재생하고, 모델 버전을 비교 평가할 수 있습니다.

> Inspired by the original [Pikachu Volleyball](https://github.com/gorisanson/pikachu-volleyball) (1997).

**Status**: v1.0.0 deployed to all 3 envs (dev/qa/prod, main reachable) · **v2.0.0 prepared on `v2.0.0-docs`** — S1 self-play league + S2 reward_model selector (shaped/sparse/learned) + S3 LSTM recurrent policy + S4 SAC-Discrete algorithm + S5 Dreamer V3 world-model (Experimental). All selectors default to v1 behavior — breaking-free migration. See [release notes](docs/release-notes/RELEASE-NOTES-v2.0.md) · [migration](docs/migrations/v1-to-v2.md) · [retrospective](docs/retrospective/v2.x-retrospective.md) · [ADRs 0014-0018](docs/adr/README.md). QA 5/5 sprint regression PASS.

## Quick Start

```bash
git clone https://github.com/shyoon-devops/pikachu-volleyball-rl.git
cd pikachu-volleyball-rl
cp .env.example .env
docker compose up --build
```

| Service | URL |
|---------|-----|
| Dashboard | http://localhost:5173 |
| API Docs | http://localhost:8000/docs |
| Backend | http://localhost:8000 |

## Architecture

**Two-server split** (since v0.2.1, commit `75fb4292`): frontend serves from a separate nginx host and reverse-proxies API/WS to the GPU server. Docker Compose 파일에서 `frontend` 서비스 제거.

```
┌─────────────────────────────────────────┐      ┌─────────────────────────────────────────┐
│   yoonbian-2 (192.168.0.248)            │      │   GPU server (192.168.0.250)            │
│   ─────────────────────────────         │      │   ─────────────────────────────         │
│   nginx (static + reverse proxy)        │◀────▶│   Backend (FastAPI)                     │
│   Built frontend (React 19 / Vite)      │      │   REST · WebSocket Hub · Services       │
│   :3000 dev  ·  :3001 qa  ·  :5173 prod │      │   :8001 dev · :8002 qa · :8000 prod     │
│                                         │      │   ┌──────────────────────────────────┐  │
│   PixiJS canvas  ·  Recharts  ·  WS     │      │   │ Game Engine (Pure Python)        │  │
│   Dashboard · Replay · Evaluation       │      │   │ Physics · Bot L1-L5 · Gym 18D/12A│  │
│                                         │      │   └──────────────────────────────────┘  │
│                                         │      │   ┌──────────────────────────────────┐  │
│                                         │      │   │ RL Pipeline (SB3 PPO)            │  │
│                                         │      │   │ Trainer · Evaluator · Callbacks  │  │
│                                         │      │   └──────────────────────────────────┘  │
│                                         │      │            │                            │
│                                         │      │   ┌────────┴─────────┐                  │
│                                         │      │   │ MongoDB 7 (motor)│                  │
│                                         │      │   │ :27018/27019/    │                  │
│                                         │      │   │ 27017 per env    │                  │
│                                         │      │   └──────────────────┘                  │
└─────────────────────────────────────────┘      └─────────────────────────────────────────┘
```

Nginx configs: `frontend/nginx-dev.conf`, `frontend/nginx-qa.conf`, `frontend/nginx-prod.conf` (per-env API/WS upstream).
Frontend 배포: `scripts/deploy-frontend.sh` — 로컬 빌드 후 yoonbian-2 rsync + nginx reload.

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | Python 3.11+ / FastAPI / Uvicorn |
| RL | Stable-Baselines3 (PPO) / Gymnasium |
| Frontend | React 19 / TypeScript / PixiJS 8.18 / Vite 8 / React Router 7.14 |
| Validation | zod (WS payload discriminated union — v1.0 A6) |
| Charts | Recharts |
| Real-time | WebSocket (training:frame / training:metrics / training:game_end / training:env_frame) |
| Database | MongoDB 7 (motor async) |
| Deploy | Docker Compose / GitHub Actions CI/CD / scripts/deploy-frontend.sh auto-advance |
| Testing | pytest + engine parity suite (11k assertions) / Vitest / Playwright visual regression |

## Key Features

**Game Engine** — Physics-based 2D volleyball, **faithful 1:1 port** of `gorisanson/pikachu-volleyball` (1997). Full state machine including `slowMotion` / `afterEndOfRound` / `beforeStartOfNextRound`. 25fps game loop. Five difficulty bot levels (L1 beginner ~ L5 perfect).

**RL Training** — **Algorithm matrix (v2)**: PPO / SAC-Discrete / Dreamer V3 world-model (Experimental) × MLP / LSTM policy × shaped_v1 / sparse_v1 / learned_shaped_v1 reward. Opponent mode: Rule ladder (L1~L5) or self-play league with Elo-ranked sampling. SB3 + sb3-contrib RecurrentPPO + vendored dreamerv3-torch. 8 parallel SubprocVecEnv with per-env frame broadcast (`training:env_frame`) and per-env game save. Extended hyperparameter form with all 5 selectors. Training runs tagged by user-entered title, propagated to model filename and downstream records.

**Web Dashboard** — Unified `/runs` navigation with Overview / Games / Evaluation sub-tabs (v1.0 ADR-0013). Live game visualization (PixiJS, original view.js port). Replay player with seek/speed, bulk-delete multi-select, batch-tab multi-env live view.

**Model Evaluator (E1-E10)** — Full stack: Elo rating (L1/L3/L5 anchors), dominance score, baseline comparator, best-model auto-selection, parallel batch CLI, markdown report generator with charts + Elo leaderboard. Async `/api/evaluation/run` with `/status/{id}` polling.

**Multi-Environment** — dev/qa/prod split across two hosts. Backend + MongoDB on GPU server via Docker Compose, frontend served via nginx on yoonbian-2. `deploy-frontend.sh` auto-advances `github/<env>` ref post-deploy.

> **Authoritative port source:** [`docs/VERSIONS.yml`](docs/VERSIONS.yml). The table below reflects curl-verified state as of 2026-04-12. If it drifts from VERSIONS.yml, VERSIONS.yml wins. Any port change requires a PR updating VERSIONS.yml, this README, and `docs/DEPLOYMENT-STATUS.md` **before** the deploy — see [WORKFLOW.md § Port Change Policy](docs/WORKFLOW.md#port-change-policy).

| Environment | Backend (GPU, 192.168.0.250) | Frontend (yoonbian-2, 192.168.0.248) | MongoDB | Status (2026-04-12 curl) |
|-------------|------------------------------|---------------------------------------|---------|--------------------------|
| dev | `:8001` | http://192.168.0.248:3000 | `:27018` (docs, unverified) | backend up, /health/live+ready ok |
| qa | `:8002` | http://192.168.0.248:3001 | `:27019` (docs, unverified) | **backend DOWN** — #38 |
| prod | `:8003` | http://192.168.0.248:3002 | `:27020` (per ops, unverified) | backend up but **pre-BE-3 code** — #37/#38 |

Frontend ports `:3000/:3001/:3002` currently serve a byte-identical bundle (`index-CAYlGd5L.js`). DevOps is confirming whether this is intended single-dist-multi-port or accidental overwrite (#38).

## Local Development

**Backend:**
```bash
cd backend && pip install -e ".[dev]"
uvicorn app.main:app --reload --port 8000
```

**Frontend:**
```bash
cd frontend && npm install && npm run dev
```

**MongoDB only:**
```bash
docker compose up mongodb
```

## Project Structure

```
backend/
  game/         Physics engine, bot, constants (faithful port of physics.js + cloud_and_wave.js)
  rl/           Gymnasium env, PPO trainer, evaluator (E1-E10), callbacks, sweep, elo, baseline_comparator,
                batch_evaluate, best_model_selector, comparison_chart, report_generator
  app/          FastAPI server (api/, ws/, services/, models/) — /runs aggregation, /evaluations CRUD,
                /evaluation/run async + status, /models bulk delete, timeseries endpoint
  tests/        pytest: physics parity (11k assertions), engine scenarios, evaluator unit, training API
frontend/src/
  components/   dashboard/ game/ replay/ evaluation/ runs/ (unified)
  shared/       ScoreCell, TimestampText, EnvChip (A5 extracted)
  hooks/        useWebSocket (+zod validated), useTrainingState
  ws/           Discriminated union + zod schema for training:* messages (A6)
  styles/       Design tokens, global CSS
scripts/        deploy (auto-advances github/<env>), promote, release, status
docs/
  adr/          ADR-0001..0013 (0011 parity port, 0012 refactor gates, 0013 unified /runs)
  design/       7 DESIGN-*.md specs (runs merged, batch tabs, eval/history drilldown, bulk delete,
                hyperparam form, training title)
  audits/       port diffs, constants inventory, state-machine cross-walk
  reports/      PM reports + notices archive
  releases/     Per-version release notes
  INDEX.md      Master catalogue of ADRs + specs + audits + reports
```

## Testing

```bash
cd backend && pytest tests/ -v --cov    # Backend
cd frontend && npm run test              # Frontend
```

## Deployment

Two-server workflow — backend + MongoDB 은 GPU 서버 Docker Compose, frontend 는 yoonbian-2 nginx 정적 서빙.

```bash
# Backend (GPU server)
scripts/deploy-dev.sh            # backend compose up (dev)
scripts/deploy-qa.sh             # backend compose up (qa)
scripts/deploy-prod.sh           # backend compose up (prod)

# Frontend (from any machine that can reach yoonbian-2 via SSH)
scripts/deploy-frontend.sh dev   # build + rsync → yoonbian-2:/var/www/...
scripts/deploy-frontend.sh qa
scripts/deploy-frontend.sh prod

# Promotion + release
scripts/promote.sh dev-to-qa     # dev → qa (git)
scripts/promote.sh qa-to-prod    # qa → prod (git)
scripts/release.sh 0.2.1         # Version tag + changelog
scripts/status.sh                # Environment status
```

Prod 승격 후에는 반드시 `main` 브랜치로 머지하고 `v0.X.Y` 태그를 `main` HEAD 에 유지해야 합니다 — [docs/WORKFLOW.md](docs/WORKFLOW.md) 참조.

## Team

| Role | Scope |
|------|-------|
| AI Engineer | Game engine, bot, RL environment |
| Trainer | PPO training pipeline, callbacks |
| Evaluator | Model evaluation, comparison |
| Backend Engineer | FastAPI, WebSocket, MongoDB |
| Frontend Engineer | React UI, hooks, API client |
| Designer | CSS design system, arcade theme |
| DevOps Engineer | Docker, CI/CD, deployment |
| QA Engineer | Test suite (unit, integration, scenario) |
| Product Manager | Versioning, docs, releases, GitHub |

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for development workflow.

## License

This project is for educational and research purposes.

---

<p align="center">
  <sub>v2.0.0 &bull; <a href="CHANGELOG.md">Changelog</a> &bull; <a href="docs/release-notes/RELEASE-NOTES-v2.0.md">Release Notes</a> &bull; <a href="docs/migrations/v1-to-v2.md">v1→v2 Migration</a> &bull; <a href="docs/DEPLOYMENT-STATUS.md">Deployment Status</a></sub>
</p>
