# DevOps 통보 — P0 match-end freeze fix dev 머지 완료

**작성자:** AI Engineer
**일시:** 2026-04-12
**우선순위:** P0 (사용자 리포트 회귀)
**대상:** DevOps

---

## 요청사항

현재 진행 중인 재배포 사이클에 **아래 커밋을 포함**해 주세요.

```
e9f72459 fix(engine): tick post-score freeze on the match-winning point
cd1e6a39 merge: P0 hotfix — match-end freeze tick
```

- `github/dev` 에 푸시 완료
- dev backend `/api/health` 200 OK (pre-redeploy)
- 변경 범위: `backend/game/engine.py` + `backend/tests/test_engine.py` 만

## 무엇이 고쳐지는가

**사용자 증상:** "Phase 2 배포 후 누가 15점 내면 게임이 거기서 멈춤. 다음 매치로 안 넘어감."

**근본 원인:** `engine.step()` 의 match-over guard 가 freeze pass-through 보다 먼저 실행됨 → score 15점에서 `post_score_freeze_frames` 이 20에 영원히 고정 → RL 콜백의 emit 루프 (`while scores < MAX or freeze > 0`) 무한 반복 → 최종 매치 리플레이 미완성 → 대시보드에서 다음 매치 안 뜸.

**수정:** `step()` 에서 freeze pass-through 를 match-over guard 보다 앞으로 reorder. ~15줄 diff.

## 검증

- engine 스위트 30/30 ✅
- 백엔드 전체 379 passed, 1 pre-existing unrelated failure (`test_api.py::test_models_empty`, HEAD 이전에도 동일 실패)
- 로컬 재현: score 14→15 후 callback 루프 20 iter 만에 정상 종료, winner=P1

## 배포 후 QA 지시 (PM 경유)

- 대시보드에서 매치 15점 도달 시 freeze 20f → 승자 표시 → 다음 매치로 정상 진행되는지 수동 확인
- RL training loop 가 episode end 를 정상 감지하는지 메트릭 대시보드 확인

## 추가 정보

- 상세 보고: `docs/REPORT-PM-20260412-P0-MATCHEND.md`
- Engine 레벨 `game_over` / `winner` 필드 추가는 **의도적으로 미구현** (기존 `result.winner` + `score >= MAX_SCORE` 로 충분)
- FE 변경 불필요

---
**end of notice.**
