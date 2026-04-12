# Development & Deployment Workflow

## Architecture: Two-Server Split

As of commit `75fb429` the stack is split across two physical hosts. **Frontend
containers no longer run locally** — the frontend is served by host-level nginx
on yoonbian-2.

```
┌─────────────────────────────────────┐      ┌──────────────────────────────┐
│ GPU server (192.168.0.250)          │      │ yoonbian-2 (192.168.0.248)   │
│ ──────────────────────────────      │      │ ──────────────────────────   │
│ • backend (docker compose)          │◄────►│ • nginx (host service)       │
│ • mongodb (docker compose)          │ HTTP │   serves /dist + proxies     │
│ • monitoring stack (optional)       │  WS  │   /api and /ws to GPU host   │
│ • RL training (pytorch + CUDA)      │      │ • no docker containers       │
└─────────────────────────────────────┘      └──────────────────────────────┘
```

### What lives where

| Service       | Host         | Runtime            | Managed by                       |
|---------------|--------------|--------------------|----------------------------------|
| backend (dev/qa/prod)  | GPU server   | docker container   | `scripts/deploy-{env}.sh`        |
| mongodb (dev/qa/prod)  | GPU server   | docker container   | `scripts/deploy-{env}.sh`        |
| frontend (dev/qa/prod) | yoonbian-2   | host nginx + /dist | `scripts/deploy-frontend.sh`     |
| monitoring     | GPU server   | docker-compose.monitoring.yml | `docker compose -f ...up` |

### Never run locally

- `pikachu-rl-*-frontend-*` containers — removed in the two-server refactor. If
  one reappears, it's an orphan from an older compose file. Kill it.

## Environments

| Environment | Backend (GPU host)   | Frontend (yoonbian-2) | MongoDB (GPU host) | Purpose                     |
|-------------|----------------------|-----------------------|--------------------|-----------------------------|
| **dev**     | :8001                | :3000                 | :27018             | 개발 & 로컬 테스트           |
| **qa**      | :8002                | :3001                 | :27019             | QA 테스트 & 검증             |
| **prod**    | :8003                | :3002                 | :27020             | 프로덕션 (훈련 & 평가)       |

> Prod backend moved from :8000 → :8003 and prod frontend from :5173 → :3002
> during the two-server refactor. Older docs/scripts referencing those ports
> are stale.

### Live inventory (what SHOULD be running)

| Container                  | State               | Host        |
|----------------------------|---------------------|-------------|
| pikachu-rl-dev-backend-1   | Up (healthy)        | GPU server  |
| pikachu-rl-dev-mongodb-1   | Up (healthy)        | GPU server  |
| pikachu-rl-qa-backend-1    | Up (healthy)        | GPU server  |
| pikachu-rl-qa-mongodb-1    | Up (healthy)        | GPU server  |
| pikachu-rl-prod-backend-1  | Up (healthy)        | GPU server  |
| pikachu-rl-prod-mongodb-1  | Up (healthy)        | GPU server  |

Any other `pikachu-rl-*` container is an **orphan** — remove it.

Verify anytime with `./scripts/status.sh` or:
```bash
docker ps --filter "name=pikachu-rl-" --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
```

## Team → Environment Mapping

| Role              | Primary Env | Workflow                                           |
|-------------------|-------------|----------------------------------------------------|
| AI Engineer       | dev         | 개발 → dev 테스트 → QA 에스컬레이션                   |
| Backend Engineer  | dev         | 개발 → dev 테스트 → QA 에스컬레이션                   |
| Frontend Engineer | dev         | 개발 → dev 테스트 → QA 에스컬레이션                   |
| Designer          | dev         | 개발 → dev 테스트 → QA 에스컬레이션                   |
| QA Engineer       | qa          | QA 환경에서 통합 테스트 & 검증                        |
| Trainer           | prod        | prod 환경에서 RL 훈련                                |
| Evaluator         | prod        | prod 환경에서 모델 평가                              |
| DevOps Engineer   | all         | 인프라 & 배포 스크립트, 모니터링                      |
| PM                | all         | prod 배포 승인 권한                                  |

## Deployment Flow

```
dev (개발) → QA (테스트) → prod (프로덕션)
    ↑            ↑             ↑
 Engineers    QA Engineer    PM 승인
```

Every promotion has **two deploy steps** — backend (GPU host) and frontend
(yoonbian-2). Missing the frontend step is a common mistake: `promote.sh`
only rebuilds the backend container, the frontend stays on yesterday's build.

### 1. Development (dev)

```bash
./scripts/deploy-dev.sh           # backend + mongo on GPU host
./scripts/deploy-frontend.sh dev  # rsync dist + nginx config to yoonbian-2
```
- dev 환경에서 기능 테스트 완료 후 QA 에스컬레이션

### 2. QA Promotion (qa)

```bash
./scripts/promote.sh dev-to-qa    # merges dev→qa, pushes, rebuilds backend
./scripts/deploy-frontend.sh qa   # DO NOT SKIP — frontend stays stale otherwise
./scripts/smoke-test.sh qa        # 13-check verification
```
- QA Engineer가 qa 환경에서: 통합 테스트, 게임 시나리오, UI/UX, 성능
- QA 통과 시 prod 에스컬레이션 요청

### 3. Production Deployment (prod)

- **PM 승인 필수** — PM이 QA 결과 확인 후 승인
```bash
./scripts/promote.sh qa-to-prod
./scripts/deploy-frontend.sh prod
./scripts/smoke-test.sh prod
```
- Trainer/Evaluator가 prod 환경에서 RL 훈련 & 평가

## Verification After Every Deploy

1. Container health — `docker ps --filter name=pikachu-rl-{env}`
2. Backend health — `curl http://localhost:800{1,2,3}/api/health`
3. Frontend reach — `curl -I http://192.168.0.248:300{0,1,2}/`
4. No orphans — `docker ps --filter name=pikachu-rl-` (should match live inventory)
5. `./scripts/smoke-test.sh {env}` — 13 checks including security headers

## Version Management

### Versioning Scheme
`v{major}.{minor}.{patch}` (SemVer)
- major: 아키텍처 변경, 호환성 깨짐
- minor: 새 기능 추가
- patch: 버그 수정, 성능 개선

### Release Process
1. QA 통과 확인
2. PM이 `scripts/release.sh {version}` 실행
3. CHANGELOG.md 자동 업데이트
4. VERSION 파일 업데이트
5. Git tag 생성
6. prod 환경 배포 (backend + frontend 모두)

## Branch Strategy

```
main (prod)
  └── qa
       └── dev
            ├── yoon/ai-engineer
            ├── yoon/backend-engineer
            ├── yoon/frontend-engineer
            ├── yoon/designer
            ├── yoon/devops-engineer
            ├── yoon/trainer
            ├── yoon/evaluator
            ├── yoon/qa-engineer
            └── yoon/product-manager
```

## Scripts Reference

| Script                         | Purpose                              | Host           |
|--------------------------------|--------------------------------------|----------------|
| `scripts/deploy-dev.sh`        | dev backend + mongo                  | GPU server     |
| `scripts/deploy-qa.sh`         | qa backend + mongo                   | GPU server     |
| `scripts/deploy-prod.sh`       | prod backend + mongo (confirms y/N)  | GPU server     |
| `scripts/deploy-frontend.sh`   | frontend build + rsync to yoonbian-2 | both           |
| `scripts/promote.sh`           | dev-to-qa / qa-to-prod merge+deploy  | GPU server     |
| `scripts/release.sh`           | CHANGELOG + VERSION + tag            | any            |
| `scripts/status.sh`            | env-by-env health summary            | any            |
| `scripts/smoke-test.sh`        | 13-check post-deploy verification    | any            |
| `scripts/setup.sh`             | 초기 환경 설정                         | any            |
| `scripts/cleanup-replays.sh`   | 리플레이 정리 (NFR2.4)                | GPU server     |
| `scripts/backup.sh`            | mongo + models 백업                   | GPU server     |
| `scripts/restore.sh`           | 백업 복원                             | GPU server     |
| `scripts/test-backup.sh`       | 백업/복원 왕복 검증                    | any            |
| `scripts/cleanup-disk.sh`      | docker prune + 체크포인트 정리          | GPU server     |

## Orphan Prevention

Deploy scripts now pass `--remove-orphans` to `docker compose up`, so
containers for services removed from the compose file are killed
automatically. They also run `docker image prune -f` (dangling only, never
`-a`) after a rebuild to reclaim untagged-layer disk.

If you see a stranger container anyway:
```bash
docker ps --filter "name=pikachu-rl-" --format "{{.Names}}"
# anything not in the live inventory table above → remove
docker rm -f <name>
docker image prune -f
```

## Documentation Requirements

모든 변경사항은 다음 문서에 반영:
- **CHANGELOG.md**: 버전별 변경 이력
- **VERSION**: 현재 버전
- **docs/PLAN.md**: 기능 명세
- **docs/WORKFLOW.md**: 배포 흐름 (이 문서)
- **CLAUDE.md**: 개발 가이드
