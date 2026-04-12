# Contributing

## Development Workflow

1. `yoon/{role}` 브랜치에서 개발
2. dev 브랜치로 머지 (PM이 관리)
3. dev → qa → prod 승격 (PM 승인)

## Branch Naming

```
yoon/{role}          # 팀원 작업 브랜치
dev                  # 통합 개발
qa                   # QA 검증
prod                 # 프로덕션
```

## Commit Convention

```
feat: 새 기능
fix: 버그 수정
refactor: 리팩토링
docs: 문서
test: 테스트
chore: 빌드/도구
perf: 성능
ci: CI/CD
```

## Code Style

- **Python**: ruff (lint + format), type hints, pytest
- **TypeScript**: ESLint, strict mode, Vitest

## Pull Requests

1. 변경사항 설명 + 테스트 결과 포함
2. PM 리뷰 후 머지
3. 기능 제안은 `docs/proposals/` 에 문서화 후 PM 검토

## Testing

```bash
cd backend && pytest tests/ -v --cov   # Backend 80%+ 목표
cd frontend && npm run test             # Frontend
```
