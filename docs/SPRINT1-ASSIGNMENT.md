# Sprint 1 (v0.2.1) — DevOps Engineer 할당

> **From**: Product Manager | **Date**: 2026-04-12
> **Branch**: feature branch → dev merge

---

## Day 1 — QA 환경 배포 + 환경 설정

### v0.2.0 QA 환경 배포 (Issue #6)

- QA 환경(:8002/:3001/:27019) 배포
- 배포 후 health check 확인

### SEC-2 환경별 CORS 설정 (Issue #10)

Backend Engineer의 CORS 수정에 맞춰 환경 파일 업데이트:
- `.env.qa`: `CORS_ORIGINS=http://localhost:3001`
- `.env.prod`: `CORS_ORIGINS=http://localhost:5173`
- Docker Compose 환경 변수 전달 확인

---

## Day 2 — 대기 + 이슈 대응

- QA 환경 모니터링
- 팀 배포 이슈 대응
- Sprint 1 완료 후 v0.2.1 QA 배포 준비

---

---

## 필수 프로세스 변경: Prod 배포 후 Main 머지

> **PM 지시 (2026-04-12)**: prod 배포 프로세스에 main 머지를 필수 단계로 포함시킬 것

**변경된 prod 배포 프로세스**:
```
1. PM prod 배포 승인
2. DevOps가 qa → prod 승격 (scripts/promote.sh qa-to-prod)
3. Prod 환경 health check 확인
4. PM에게 배포 완료 보고
5. ★ PM이 prod → main 머지 실행
6. ★ main에 버전 태그 생성 (v{version})
7. ★ git push github main --tags
8. 릴리스 노트에 main 머지 완료 기록
```

**5~8번은 prod 배포 완료 후 반드시 수행해야 하며, 이 단계가 끝나야 릴리스가 최종 완료된 것으로 간주됩니다.**

배포 스크립트(`scripts/deploy-prod.sh` 또는 `scripts/promote.sh`)에 main 머지 단계를 안내하는 로그 또는 리마인더 출력을 추가해 주세요:
```bash
echo "========================================"
echo "  REMINDER: prod → main 머지 + 태그 필요"
echo "  git checkout main && git merge prod"
echo "  git tag v{version} && git push github main --tags"
echo "========================================"
```

---

## 참고
- 배포 전 PM 승인 필요 (prod는 Project Manager 최종 승인)
- 배포 완료 시 PM에게 보고: `배포 요청: [env] [ver] [desc]` 형식
- **prod 배포 후 main 머지 + 태그는 필수 단계** (누락 시 릴리스 미완료)
