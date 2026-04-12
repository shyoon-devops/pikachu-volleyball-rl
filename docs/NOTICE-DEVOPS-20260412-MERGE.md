# NOTICE — dev 머지 추가분 (현재 재배포 사이클 포함 요청)

**수신:** DevOps Engineer
**발신:** AI Engineer
**일시:** 2026-04-12
**긴급도:** 현재 3개 환경 재배포 진행 중 — 이번 사이클에 포함 요청

---

## 요지

방금 전 `github/dev` 에 추가 머지 완료 (`a0dafa30`). DevOps 가 지금 굴리고 있는 재배포 사이클에 **이 커밋까지 포함해서 빌드**되도록 알림.

## 최신 dev tip

```
a0dafa30 merge: integrate ai-engineer sky-stripe fix + FE/BE notices  ← 신규 tip
b00564be Merge remote-tracking branch 'github/dev' into yoon/devops-engineer
7508f7ae chore(versions): Designer D11-D15 + BE perf/dead-letter redeploy
ca4cb608 fix(frame): seed last_frame at training start so /current_frame returns 200
```

## 신규 포함 내용 (merge 에서 딸려 들어온 3커밋)

| 커밋 | 내용 | 배포 영향 |
|------|------|----------|
| `fb197f89` | docs: PM report | 문서만 — 빌드 영향 없음 |
| `ff24cc9a` | fix(canvas): NEAREST 텍스처 필터 (sky-stripe) | **FE 빌드 재실행 필요** — `GameCanvas.tsx` 수정 |
| `a8582e1a` | docs: FE/BE 연동 notice | 문서만 |

## 주요 검증

- `npx tsc --noEmit` → 0 error
- `npm run build` → 성공 (839 KB gzipped 248 KB)
- `npx vitest run` → 13 파일 / 99 테스트 통과 (신규 `GameCanvas.pixel-art.test.ts` 4건 포함)

## 배포 체크 요청

FE 번들 해시가 바뀌므로:

1. 재배포 후 `dev` FE 번들 재생성 여부 확인
2. 캔버스 로드 후 sky 영역 스크린샷 1장 — RGB 수직 스트라이프 사라졌는지 시각 확인 (디자이너 QA 대기)
3. `/api/health` 200 확인 (BE는 변경사항 없지만 dev 빌드 sanity check)

## 배포 대상

- **dev**: 포함 ✅
- **qa**: PM 승인 후 (현재 배포 중인 버전에 이번 커밋 포함되는지는 DevOps 판단)
- **prod**: 별도 PM 릴리스 승인 대기

## 롤백

순수 렌더러 설정 변경 (코드 3줄) + 문서. 이상 동작 시 `ff24cc9a` 만 revert 하면 이전 상태로 복구됨. `982e3a80` 와 `d2436993` 는 dev 에 이미 머지되어 별도 revert 대상 아님.

---
**문의:** AI Engineer / yoon/ai-engineer 브랜치
