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
6. prod 환경 배포

## Documentation Requirements

모든 변경사항은 다음 문서에 반영:
- **CHANGELOG.md**: 버전별 변경 이력
- **VERSION**: 현재 버전
- **docs/PLAN.md**: 기능 명세
- **CLAUDE.md**: 개발 가이드
