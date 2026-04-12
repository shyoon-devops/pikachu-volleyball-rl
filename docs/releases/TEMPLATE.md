# Release Note: v{VERSION}-{ENV}

> 파일명 규칙: `v{major}.{minor}.{patch}-{dev|qa|prod}.md`
> 예: `v0.2.1-qa.md`, `v0.2.1-prod.md`
>
> 이 문서는 매 환경 배포 시 새로 생성. dev/qa/prod 각 환경별로 별도 파일 유지.

---

## Summary

| Field | Value |
|-------|-------|
| **Version** | {0.2.1} |
| **Environment** | {QA :8002 / :3001 / :27019} |
| **Date** | {YYYY-MM-DD} |
| **Tag** | `v{0.2.1}` |
| **Commit** | `{sha}` ({branch}) |
| **Base** | `{prev-sha}` ({prev-tag}) |
| **Deployed By** | {DevOps Engineer} |
| **Release Manager** | {Product Manager} |

---

## What's Included

> 커밋 SHA와 이슈 번호를 항상 함께 남길 것. 미래의 나/팀이 왜 이 변경이 들어갔는지 추적 가능해야 함.

### Features
- `{sha}` {한줄 설명} ([#{issue}](../../issues/{issue}))

### Bug Fixes
- `{sha}` {한줄 설명} ([#{issue}](../../issues/{issue}))

### Security
- `{sha}` {CRITICAL/HIGH} — {설명} ([#{issue}](../../issues/{issue}))

### Refactors / Infra
- `{sha}` {설명}

### Breaking Changes
- {없으면 "None"} — 있을 경우 migration 절차 명시

---

## Metrics Snapshot (릴리스 시점)

> `docs/METRICS.md`의 gate와 일치시킬 것. 자동화 전에는 수기로 기록.

| Metric | Value | Target | Pass/Fail |
|--------|-------|--------|-----------|
| Backend coverage | {%} | 80% | {P/F} |
| Frontend coverage | {%} | 60% | {P/F} |
| bandit HIGH issues | {count} | 0 | {P/F} |
| npm audit HIGH | {count} | 0 | {P/F} |
| CI 연속 성공 | {count}회 | — | — |
| Open CRITICAL issues | {count} | 0 | {P/F} |

---

## Deployment Steps Executed

```bash
# 실제 수행한 명령어를 복사-붙여넣기
git checkout {branch} && git pull
scripts/promote.sh {src}-to-{dst}
scripts/release.sh {version}       # QA/prod 태그 컷 시에만
docker compose -f docker-compose.{env}.yml up --build -d
```

**Pre-deploy state:**
- {env} backend: `{sha}`
- DB 백업: `{yes/no, path}`

**Post-deploy state:**
- {env} backend: `{new_sha}`
- 컨테이너 상태: `{docker ps 요약}`

---

## Health Check (머지/배포 후 필수)

- [ ] `docker ps --filter name=pikachu-rl-{env}` — 전 컨테이너 healthy
- [ ] `curl http://localhost:{backend-port}/api/health` — 200 OK + 세부 응답 스키마 확인 (BE-3)
- [ ] Frontend 로드 확인 — `http://localhost:{frontend-port}`
- [ ] WebSocket 연결 + ping/pong 동작
- [ ] MongoDB 연결 — replica count, 주요 컬렉션 존재
- [ ] 로그에 ERROR/CRITICAL 스파이크 없음 (`docker logs --tail 200`)

---

## QA Verification (QA 배포에 한함)

- [ ] QA Engineer 검증 리포트 작성: `docs/qa-reports/v{version}-qa.md`
- [ ] Sprint 스코프 항목 기능 검증
- [ ] 회귀 테스트 스위트 실행 (prior bugs)
- [ ] 성능 smoke test (주요 엔드포인트 p95)
- [ ] 보안 스캔 결과 링크
- [ ] QA 최종 판정: **PASS / FAIL / PASS-WITH-WARNINGS**

---

## Prod Promotion Decision (prod 배포 전)

- [ ] PM이 QA 리포트 검토
- [ ] Open CRITICAL/HIGH 이슈 확인 (0건이어야 함)
- [ ] Prod 배포 승인 서명 (PM): {name} @ {timestamp}
- [ ] 배포 윈도우 예약 (다운타임 영향도 확인)

---

## Main Branch Merge (prod 배포 후 필수)

> 이 단계 누락 금지. 릴리스 워크플로우 강제 사항.

- [ ] `prod → main` 머지 수행 (`git merge github/prod --no-ff`)
- [ ] 버전 태그 `v{version}` main에 생성
- [ ] `git push github main --tags` 완료
- [ ] GitHub Release 노트 발행 (이 문서 내용 복사)
- [ ] 이 섹션 체크 완료 → 릴리스 최종 완료

---

## Known Issues (릴리스 시점)

- [#{issue}] {설명} — {영향도, 회피 방법}
- 혹은 "None"

---

## Rollback Plan

문제 발생 시 복구 절차:

```bash
# 1. 이전 버전 태그로 복구
docker compose -f docker-compose.{env}.yml down
git checkout v{prev-version}
docker compose -f docker-compose.{env}.yml up --build -d

# 2. DB 롤백 필요한 경우
scripts/restore-mongo.sh backup/mongo/{YYYY-MM-DD}.archive.gz

# 3. 롤백 기록
docs/incidents/{YYYY-MM-DD}-{slug}.md 작성
```

**Rollback target version**: `v{prev-version}` (`{prev-sha}`)

---

## Post-Release Checklist

- [ ] `docs/DEPLOYMENT-STATUS.md` 업데이트 (current version + commit + tag)
- [ ] `CHANGELOG.md` 에서 Unreleased → 해당 버전 섹션 이동
- [ ] 관련 GitHub Issue 종료 (해결 커밋 링크 코멘트 필수)
- [ ] 스프린트 추적 문서에 완료 로그 추가
- [ ] 다음 스프린트 킥오프 준비

---

## References

- [CHANGELOG.md](../../CHANGELOG.md#{version})
- [METRICS.md](../METRICS.md)
- [WORKFLOW.md](../WORKFLOW.md)
- [이전 릴리스 노트](./)
