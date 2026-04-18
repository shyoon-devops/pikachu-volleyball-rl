# PM 보고 — gorisanson/pikachu-volleyball 물리 포팅 완료

**작성자:** AI Engineer
**일시:** 2026-04-13
**상태:** 로컬 커밋 4건 + push 완료, **dev 머지 보류 (법적 판단 필요)**
**브랜치:** `yoon/ai-engineer` → github/yoon/ai-engineer

---

## TL;DR

- PM 지시 5개 단계 중 **4개 커밋으로 완수** (에셋 단계는 byte-identical 이라 별도 커밋 대신 attribution 에 흡수).
- 테스트 **391 passed + 1 xfailed** (L5 vs L3 봇 순서 — 물리 변경으로 봇 재튜닝 필요, xfail 로 추적).
- **중대 정정**: 원본 레포는 MIT 가 아니라 UNLICENSED. ATTRIBUTION.md 로 정정 공지 + 커밋 1 메시지의 "MIT" 문구 retract.
- **dev 머지는 PM 결정 대기** — 법적 판단 + QA 재현 확인 필요.

---

## 커밋 4건

```
8add0ea6 test(golden): 10-scenario + determinism regression pinning for port
4b161103 docs(license): accurate attribution for reverse-engineered physics port
d8dc8bb6 port(view): gameEnd 211f intro-return flow, drop post-score freeze
1fb72169 port(physics): faithful engine from gorisanson physics.js
```

### 1. `port(physics)` — 1:1 물리 포팅

`backend/game/engine.py` 재작성. 원본 physics.js 의 subroutine 을 함수 단위로 매핑:

| 우리 코드 | 원본 (physics.js) |
|---|---|
| `_update_ball_and_world` | `processCollisionBetweenBallAndWorldAndSetBallPosition` |
| `_update_player` | `processPlayerMovementAndSetPlayerPosition` |
| `_check_ball_player_collision` | `isCollisionBetweenBallAndPlayerHappened` + `processCollisionBetweenBallAndPlayer` |
| `_calculate_expected_landing_point_x` | `calculateExpectedLandingPointXFor` |
| `_process_game_end_frame_for` | `processGameEndFrameFor` |
| `_rand` | `rand()` (rand.js) |

**핵심 변경:**
- `PlayerState.state` (0-6) 를 진실의 원천으로. 기존 `is_jumping/is_diving/is_power_hitting` 은 파생 필드로 보존 (bot.py, env.py 호환).
- `state=2` (jumping+power_hit) dwell window 추가 — 원본에서는 10프레임간 power-hit 상태 유지. 기존 코드는 즉시-only였음.
- 무조건 중력 (기존에는 is_jumping/is_diving gated).
- `fine_rotation` (0-50) 추가, `rotation` = fine_rotation//10 (sprite frame 0-5 — 기존은 degrees 0-360 으로 엉뚱하게 썼음).
- `_trunc_div` 헬퍼로 JS `(a/b)|0` 의 truncate-toward-zero 의미 재현.
- `expected_landing_point_x` 콜리전 때마다 갱신 (원본 봇 AI + 장래 활용).
- `seed` 생성자 파라미터로 RNG 시드 가능 (골든 테스트 결정성 확보).

**기존 L1-L5 봇은 그대로** (PM 지시). 원본의 `letComputerDecideUserInput` 은 포팅 안 함.

### 2. `port(view)` — freeze 제거 + gameEnd 211f

원본 pikavolley.js 의 `gameEnd` 상태머신 도입:

- `POST_SCORE_FREEZE_FRAMES=20` 제거.
- `is_game_ended` + `game_end_frame_counter` 추가, `GAME_END_FRAMES=211`.
- MAX_SCORE 도달 시: is_game_ended=True, winner/loser flag 세팅, 211 프레임간 물리 계속 (공 튀김 + 승자/패자 포즈). 211 후 상태 영구 고정.
- **mid-match 득점은 즉시 swap** — 20프레임 freeze 는 원본에 없음. 5f fade + 30f ready 는 display layer 책임이지 engine 책임 아님.

consumer 업데이트:
- `backend/rl/env.py` — `post_score_freeze=False` 제거 (기본 동작이 곧 그 의도).
- `backend/rl/callbacks.py` — exit 루프 `is_game_ended AND counter < 211` 로 변경. frame payload 에 `is_game_ended` + `game_end_frame_counter` 담음.
- `backend/app/services/replay_service.py` — 구 리플레이 호환 위해 `post_score_freeze_frames` default 유지 + 새 필드 추가.

P0 freeze regression (커밋 `e9f72459`) 의 근본 해결 = freeze 개념 자체를 원본에 없던 것이므로 제거.

### 3. `docs(license)` — attribution 정정

**STOP 했던 이슈**: PM 지시 원문의 "원본 레포 자체는 MIT" 가 사실과 다름. 실제 확인:

- `/tmp/pikachu-original/` 에 LICENSE 파일 없음.
- `package.json`: `"license": "UNLICENSED"`.
- README 에도 MIT 언급 전무.
- 원본 저자 gorisanson 본인이 "reverse engineering the core parts of the machine code of the original game" 이라고 README 에 기재 — 원본 1997 게임 저작권자 (© SACHI SOFT / SAWAYAKAN Programmers / Satoshi Takenouchi) 에게 근본 권리.

**조치:**
- `ATTRIBUTION.md` 레포 루트에 생성 — 정확한 provenance (UNLICENSED + reverse-engineered + 1997 저작권 chain), 우리가 포팅한 부분 vs 원본 작업 명확히 구분, MIT 주장 retract.
- `docs/NOTICE-ATTRIBUTION-CORRECTION.md` — 커밋 1 메시지 "MIT" 문구 정정 감사 흔적.
- `backend/game/engine.py` 모듈 docstring — "MIT-licensed" 문구 제거, ATTRIBUTION.md 로 redirect.
- **git history 는 재작성 안 함** — 커밋 `1fb72169` 메시지는 그대로 남음. 히스토리 재작성하면 dev/main 오염됨. ATTRIBUTION.md 가 정정의 권위 있는 출처.

### 4. `test(golden)` — 10 시나리오 + 결정성 pin

`backend/tests/test_golden_scenarios.py` — 10개 핵심 물리 path + 4개 시드에 대한 결정성 meta-test. 현재 Python 포팅이 진실의 원천 (JS harness 없어서 frame-accurate 원본 검증은 불가).

시나리오: 서브 궤적 / 플레이어 반사 / 파워히트 smash / 다이빙 트리거 / 다이빙 착지 / 네트 꼭대기 / 네트 측면 / 천장 / 득점 swap / gameEnd 211f.

---

## 에셋 ("port(assets)" 단계 — 별도 커밋 없음)

확인 결과 현재 `frontend/public/assets/` 의 모든 에셋이 `/tmp/pikachu-original/src/resources/assets/` 과 **byte-identical** (md5 일치):

| 파일 | md5 일치 |
|---|---|
| `sprite_sheet.png` + `sprite_sheet.json` | ✅ |
| `sounds/WAVE140_1.wav` … `WAVE146_1.wav` | ✅ (7개 모두) |
| `sounds/bgm.mp3` | ✅ |

실질 교체 작업 없어 별도 커밋 대신 ATTRIBUTION.md 에 provenance 기재로 흡수.

**주의**: 이 에셋들은 원본 gorisanson 저자가 아니라 1997 게임 원저작권자 (SACHI SOFT 등) 에게 권리. 배포 범위 확대 시 재검토 필요.

---

## 검증

- 백엔드 391 passed, 1 xfailed (L5 vs L3 봇 순서 — bot param 재튜닝 대기)
- 골든 시나리오 14/14 ✅
- ruff clean (pre-existing unused import 1건 외)
- 3개 docstring 기반 provenance chain 명시

---

## 알려진 Follow-ups (이번 커밋에서 해결 안 함)

**봇 재튜닝 (긴급도 중)**
- 물리 변경으로 L1-L5 파라미터 ladder 가 더 이상 L5>L3 majority 를 만들어내지 못함. test_l5_comfortably_beats_l3 xfail 로 추적.
- `backend/game/bot.py` 의 reaction_delay / prediction_error / power_probability 재피팅 필요.
- PM 이 이전에 승인한 "RL checkpoint re-run" 사이클에 맞춰 진행 가능.

**RL 체크포인트 재학습 (PM 이미 승인)**
- 물리 바뀌어서 기존 PPO 학습 이력 무효. Trainer 에게 재학습 지시 필요.

**FE (rotation 시맨틱 변경)**
- ball.rotation 이 degrees(0-360) → sprite-frame index(0-5) 로 바뀜. FE 에서 rotation 을 어떻게 해석하는지 확인 필요. 만약 degrees 가정 코드가 있다면 시각적 회전이 느려지거나 끊길 수 있음. QA 에서 눈으로 봐야 함.

**법적 (PM/사업 결정)**
- 배포 범위 확대 전 gorisanson 연락해서 permissive license 부여 요청 검토.
- 장기: 에셋 자체 제작 + 물리 clean-room 재구현으로 외부 derivation 제거 검토.

---

## dev 머지 보류 사유

다음 중 어느 것이든 사실이 되기 전까지 dev 머지 대기 권장:

1. **법적 판단** — UNLICENSED 원본에서 포팅한 코드를 dev 에 머지해 공개적으로 배포/학습 이력에 남기는 것에 대한 PM/회사 허용 여부.
2. **FE rotation 시각 회귀 검증** — 대시보드에서 공 회전 정상 보이는지.
3. **봇 재튜닝 1차** — xfail 테스트 풀어놓고 진행할지, 묶어서 머지할지 방침.

PM 결정 주시면 즉시 dev 머지 + DevOps 통보.

---

## 파일 변경 요약

| 파일 | 변경 |
|---|---|
| `backend/game/engine.py` | 전면 재작성 (1:1 port + freeze 제거 + gameEnd 211f) |
| `backend/rl/env.py` | post_score_freeze 파라미터 제거 |
| `backend/rl/callbacks.py` | exit 루프 + frame payload |
| `backend/app/services/replay_service.py` | 구/신 스키마 defaults 공존 |
| `backend/tests/test_engine.py` | TestPostScoreFreeze → TestGameEnd 재작성 |
| `backend/tests/test_physics.py` | 기존 API (is_diving 등) → state 기반으로 |
| `backend/tests/test_bot.py` | L5 vs L3 xfail |
| `backend/tests/test_coverage_gaps.py` | 새 key set |
| `backend/tests/test_golden_scenarios.py` | 신규 — 10 시나리오 + 결정성 |
| `ATTRIBUTION.md` | 신규 — 정확한 provenance |
| `docs/NOTICE-ATTRIBUTION-CORRECTION.md` | 신규 — MIT 주장 정정 |

---
**end of report.**
