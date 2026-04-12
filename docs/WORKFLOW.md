# Development & Deployment Workflow

## Environments

> **Authoritative source for ports & deployed versions:** [`docs/VERSIONS.yml`](VERSIONS.yml). The table below is a quick reference; on conflict VERSIONS.yml wins. See [§ Port Change Policy](#port-change-policy) and [§ Post-Deploy Doc Update](#post-deploy-doc-update) below.

| Environment | Backend host | Backend port | Frontend host | Frontend port | MongoDB | Purpose |
|-------------|--------------|--------------|---------------|---------------|---------|---------|
| **dev** | GPU (192.168.0.250) | `:8001` | yoonbian-2 (192.168.0.248) | `:3000` | `:27018` | 개발 & 로컬 테스트 |
| **qa** | GPU (192.168.0.250) | `:8002` | yoonbian-2 (192.168.0.248) | `:3001` | `:27019` | QA 테스트 & 검증 |
| **prod** | GPU (192.168.0.250) | `:8003` | yoonbian-2 (192.168.0.248) | `:3002` | `:27020` | 프로덕션 (훈련 & 평가) |

포트/아키텍처는 2026-04-12 에 two-server 구조 + 새 포트로 이행했습니다. 이전 문서의 `:8000 / :5173 / :27017` 기재는 더 이상 유효하지 않습니다.

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
- **docs/VERSIONS.yml**: **각 환경 실제 배포 상태** (SoT — 아래 § Post-Deploy Doc Update 규칙 적용)
- **docs/DEPLOYMENT-STATUS.md**: 환경별 현재 상태 + 대기 액션
- **docs/PLAN.md**: 기능 명세
- **CLAUDE.md**: 개발 가이드

---

## Post-Deploy Doc Update

**(강제 규칙 — 2026-04-12 제정, 문서 drift 재발 방지)**

배포를 수행한 엔지니어는 **배포 완료 후 30분 이내**에 다음 파일을 실제 배포 값으로 업데이트하고 커밋/푸시해야 합니다.

### 필수 업데이트 대상
1. **`docs/VERSIONS.yml`** — 해당 env 의 `commit`, `image`, `built_at`, `deployed_at`, `status`, (프런트 배포 포함 시) `bundle` 전부 실제 값으로. `last_file_update` 갱신.
2. **`docs/DEPLOYMENT-STATUS.md`** — "Verified Runtime State" 표와 Release History 갱신.
3. **`CHANGELOG.md`** — prod 배포인 경우 해당 버전 섹션 헤더를 `(prod 배포 완료, YYYY-MM-DD)` 로 변경.
4. prod 배포인 경우 `docs/releases/v{version}-prod.md` 작성.

### 30분 초과 시 제재
- **다음 배포 승인 자동 취소.** PM 은 VERSIONS.yml 의 `last_file_update` 와 실제 docker 배포 시각을 대조해 위반 여부를 판단합니다.
- 위반 기록은 `docs/DEPLOYMENT-STATUS.md § What PM got wrong` 섹션에 동등한 DevOps 측 항목으로 기재됩니다.
- 반복 위반(연속 2회) 시 해당 엔지니어의 단독 배포 권한 정지, PM 직접 승인 요청 후 공동 실행으로 전환.

### 검증
- PM 은 배포 보고를 받는 즉시 다음 curl 3종을 실행해 VERSIONS.yml 과 대조합니다.
  - `curl -s http://<backend>/api/health`
  - `curl -s http://<backend>/api/health/live` (BE-3 이후)
  - `curl -s http://<frontend>/ | grep -oE 'assets/index-[A-Za-z0-9_-]+\.js'`
- 불일치 발견 시 배포는 실패 처리, 즉시 롤백 요청.

---

## Port Change Policy

**(강제 규칙 — 2026-04-12 제정)**

다음 중 하나라도 변경되는 배포는 **PM 사전 승인 없이 금지**합니다.
- 백엔드 listen port
- 프런트엔드 서빙 port
- MongoDB port
- 호스트 (GPU 서버 ↔ yoonbian-2 등)

### 절차
1. **배포 전 PR**: DevOps 는 다음 파일을 **동일 PR** 에서 새 포트로 갱신합니다.
   - `docs/VERSIONS.yml`
   - `docs/DEPLOYMENT-STATUS.md`
   - `README.md`
   - `docs/WORKFLOW.md` (본 파일의 Environments 표)
   - 관련 `scripts/deploy-*.sh`, nginx config, docker-compose
2. **PM 승인**: PM 이 PR 승인 + GitHub 배포 이슈에 `port-change-approved` 라벨 부착.
3. **배포 실행**: 승인 후에만 deploy 스크립트 실행.
4. **위반 시**: 즉시 롤백 지시 + 해당 배포의 모든 artifact (이미지, 태그) 삭제/재생성.

### 예외 없음
긴급 hotfix 라도 포트 변경은 본 절차를 거쳐야 합니다. 긴급하면 PM 채널로 즉시 호출해 최소 5분 내 승인 가능. 단독 변경은 불허.

### 현재 상태 기록 (2026-04-12)
다음 포트 변경이 사전 문서 업데이트 없이 실행되었습니다 — 재발 방지를 위해 기록.
- prod backend: `:8000` → `:8003`
- prod frontend: `:5173` → `:3002`
- prod mongodb: `:27017` → `:27020`
- qa backend: 현재 DOWN (이유 미보고 — #38)

본 규칙은 이 사건의 후속 조치로 제정되었습니다.
