# NOTICE — Engine FX/Freeze Fields Now Live on dev

**수신:** Backend Engineer, Frontend Engineer
**발신:** AI Engineer
**일시:** 2026-04-12
**dev 머지 커밋:** `a0dafa30` (포함 커밋: `fb197f89 ff24cc9a a8582e1a d2436993 982e3a80 6ff911d9`)
**상태:** 소비 가능 (ready to consume)

---

## 요점

아래 엔진 상태 필드들은 dev 브랜치에 머지 완료되어 **WS 프레임 페이로드에서 즉시 읽을 수 있습니다.** FE/BE 양쪽 모두 추가 요청 없이 바로 소비해도 됩니다.

| 필드 | 타입 | 위치 | 의미 |
|------|------|------|------|
| `ball.punch_effect_x` | int | `frame.ball` | 그라운드 임팩트 원 중심 X |
| `ball.punch_effect_y` | int | `frame.ball` | 그라운드 임팩트 원 중심 Y |
| `ball.punch_effect_radius` | int | `frame.ball` | 임팩트 원 반경 (프레임마다 감소, 0 되면 비표시) |
| `ball.is_power_hit` | bool | `frame.ball` | P1/P2 파워 히트 발동 프레임 (rising edge 로 취급) |
| `frame.is_round_over` | bool | `frame` | 랠리 종료 프레임 |
| `frame.post_score_freeze_frames` | int | `frame` | 득점 후 프리즈 카운트다운 (0 되면 다음 라운드) |

## 근거 (소스)

- `backend/game/engine.py:72-74` — `punch_effect_x/y/radius` 필드 정의
- `backend/game/engine.py:110` — `post_score_freeze_frames`
- `backend/game/engine.py:137-148` — `post_score_freeze` 옵션 생성자
- `backend/game/engine.py:202-204, 220-224` — 프리즈 중 필드 전파 로직

## 연동 계약서

**FE 측 D11-D13 / D15 CSS 클래스 매핑은 `docs/NOTICE-FX-PAYLOAD-READY.md` 참고.** 해당 문서에 trigger/action 계약 (rising-edge 감지, 반경 카운트다운, `is_power_hit` 스파크 등) 모두 정리되어 있습니다.

## 리플레이 back-compat

레거시 msgpack 리플레이는 `_backfill_frame` 이 기본값 (0, False) 을 채워주므로 FE 리플레이 뷰어는 신/구 둘 다 그대로 읽을 수 있습니다.

## 15점 프리즈 (사용자 리포트 건)

15점 마지막 득점 프레임 비가시 이슈도 `6ff911d9` 에서 해결. `frame.post_score_freeze_frames > 0` 동안 공이 바닥에 있는 상태가 유지되므로 FE는 기존처럼 프레임을 그리면 됩니다. 특별한 클라이언트 로직 불필요.

## 봇 난이도 상향 (무관 참고)

`d2436993` 에서 L1-L5 봇 파라미터 상향됨. FE 측 UI 변경 없음 — 난이도 선택 메뉴가 이미 1-5 레벨을 지원 중.

## 질문/이슈

dev 환경 재배포는 DevOps 측에서 진행 중. 배포 완료 후 `/api/health` 200 확인 후 연동 개시 권장.

---
**문의:** AI Engineer / yoon/ai-engineer 브랜치
