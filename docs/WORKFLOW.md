# Development & Deployment Workflow

## Environments

| Environment | Backend | Frontend | MongoDB | Purpose |
|-------------|---------|----------|---------|---------|
| **dev** | :8001 | :3000 | :27018 | 개발 & 로컬 테스트 |
| **qa** | :8002 | :3001 | :27019 | QA 테스트 & 검증 |
| **prod** | :8000 | :5173 | :27017 | 프로덕션 (훈련 & 평가) |

## Team → Environment Mapping

| Role | Primary Env | Workflow |
|------|------------|---------|
| AI Engineer | dev | 개발 → dev 테스트 → QA 에스컬레이션 |
| Backend Engineer | dev | 개발 → dev 테스트 → QA 에스컬레이션 |
| Frontend Engineer | dev | 개발 → dev 테스트 → QA 에스컬레이션 |
| Designer | dev | 개발 → dev 테스트 → QA 에스컬레이션 |
| QA Engineer | qa | QA 환경에서 통합 테스트 & 검증 |
| Trainer | prod | prod 환경에서 RL 훈련 |
| Evaluator | prod | prod 환경에서 모델 평가 |
| PM (Project Manager) | all | prod 배포 승인 권한 |

## Deployment Flow

```
dev (개발) → QA (테스트) → prod (프로덕션)
     ↑            ↑             ↑
  Engineers    QA Engineer    PM 승인
```

### 1. Development (dev)
- 엔지니어들이 각자 브랜치에서 개발
- `scripts/deploy-dev.sh`로 dev 환경에 배포
- dev 환경에서 기능 테스트 완료 후 QA 에스컬레이션

#### 필수: dev 머지 후 Health Check (머지한 사람 책임)

**dev에 코드를 머지한 사람은 반드시 아래를 즉시 확인해야 합니다:**

```bash
# 1. 컨테이너 상태 확인
docker ps --filter name=pikachu-rl-dev
# → STATUS가 (healthy) 인지 확인. (health: starting)이면 30초 대기 후 재확인

# 2. API health check
curl -s http://localhost:8001/api/health
# → {"status": "ok"} 반환 확인

# 3. 이상 시 로그 확인
docker logs pikachu-rl-dev-backend-1 --tail 30
```

**새 의존성(pip 패키지) 추가 시**: Docker 이미지 재빌드 필수
```bash
docker compose -f docker-compose.dev.yml build backend
docker compose -f docker-compose.dev.yml up -d backend
```

**unhealthy 발견 시**: PM에게 즉시 보고 + 원인 파악 + 수정

### 2. QA Escalation (qa)
- `scripts/promote.sh dev-to-qa`로 dev → qa 승격
- QA Engineer가 qa 환경에서:
  - 통합 테스트 실행
  - 게임 시나리오 검증
  - 프론트엔드 UI/UX 검증
  - 성능 테스트
- QA 통과 시 prod 에스컬레이션 요청

### 3. Production Deployment (prod)
- **PM 승인 필수** — PM이 QA 결과 확인 후 승인
- `scripts/promote.sh qa-to-prod`로 qa → prod 승격
- Trainer/Evaluator가 prod 환경에서:
  - RL 훈련 실행 & 모니터링
  - 모델 평가 & 비교

### 4. Main Merge & Tag (필수 — prod 배포 후 즉시)
- **prod 배포 완료 후 반드시 main 브랜치에 머지**
- `git checkout main && git merge prod` 실행
- 버전 태그 생성: `git tag v{version}` (main 위에)
- `git push github main --tags`
- 릴리스 노트에 main 머지 완료 기록
- **이 단계가 완료되어야 릴리스가 최종 완료된 것으로 간주**

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
5. prod 환경 배포
6. **prod → main 머지** (필수)
7. **main에 버전 태그 생성** (`v{version}`)
8. **GitHub push** (`main` + tags)
9. 릴리스 노트에 main 머지 완료 기록

## Branch Strategy

```
main (prod)
  └── qa
       └── dev
            ├── yoon/ai-engineer        ✅ merged to dev
            ├── yoon/trainer             ✅ merged to dev
            ├── yoon/evaluator           ✅ merged to dev
            ├── yoon/backend-engineer    ✅ merged to dev
            ├── yoon/frontend-engineer   🔄 refactoring (1 commit ahead of dev)
            ├── yoon/designer            🔄 refactoring (1 commit ahead of dev)
            ├── yoon/devops-engineer     🔄 enhancement (1 commit ahead of dev)
            ├── yoon/qa-engineer         ✅ merged to dev
            └── yoon/product-manager     📋 docs & release management
```

## Scripts Reference

| Script | Purpose | Usage |
|--------|---------|-------|
| `scripts/deploy-dev.sh` | dev 환경 배포 | `./scripts/deploy-dev.sh` |
| `scripts/deploy-qa.sh` | QA 환경 배포 | `./scripts/deploy-qa.sh` |
| `scripts/deploy-prod.sh` | prod 환경 배포 | `./scripts/deploy-prod.sh` |
| `scripts/promote.sh` | 환경 간 승격 | `./scripts/promote.sh dev-to-qa` |
| `scripts/release.sh` | 릴리스 실행 | `./scripts/release.sh 0.2.0` |
| `scripts/status.sh` | 환경 상태 확인 | `./scripts/status.sh` |
| `scripts/setup.sh` | 초기 환경 설정 | `./scripts/setup.sh` |
| `scripts/cleanup-replays.sh` | 리플레이 정리 | `./scripts/cleanup-replays.sh` |

## Documentation Requirements

모든 변경사항은 다음 문서에 반영:
- **CHANGELOG.md**: 버전별 변경 이력
- **VERSION**: 현재 버전
- **docs/PLAN.md**: 기능 명세
- **CLAUDE.md**: 개발 가이드
