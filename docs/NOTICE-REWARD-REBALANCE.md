# AI Engineer → Trainer: Reward rebalance merged to dev

> **Date**: 2026-04-12 | **From**: AI Engineer
> **To**: Trainer | **Priority**: High — rerun training baseline

---

## 요약

`backend/rl/env.py` reward function 재조정이 `dev`에 머지되었어 (PR [#40](https://github.com/shyoon-devops/devops-engineer/pikachu-volleyball-rl/pull/40)).
기존 500K-step 체크포인트는 **reward signature가 바뀌었으므로 재사용 불가**. 베이스라인 재학습 필요.

## 변경된 reward weights

| Signal | Old | New | 이유 |
|---|---|---|---|
| Game win | +20 | **+50** | Terminal 보상이 cumulative shaping을 압도하도록 |
| Game loss | -20 | **-50** | 대칭 |
| Score / Concede | ±10 | ±10 | 유지 |
| Approach ball | 0.05/f | **0.02/f** | Shaping farming 방지 |
| Ready position | 0.01/f | **0.005/f** | 동일 |
| Stall penalty | -0.03/f | **-0.05/f** | Dead rally 비용 강화 |
| Rally timeout | -5.0 | **-12.0** | 단일 concede(-10)보다 커야 함 |
| Touch 1st / 2nd / 3rd+ | +3/+1/-2 | +3/+1/-2 | 유지 (f8ea6126 anti-toss 작업 보존) |
| Net crossing | +2 | +2 | 유지 |
| **Offensive pressure (NEW)** | — | **+0.02/f** | 공이 네트 위 + 상대 코트 + vx>0 일 때. 거리 감쇠 |

## Root cause

500K steps 학습해도 승률이 낮았던 원인: 3000-step episode 동안 누적 shaping reward가 **단일 승리 bonus(+20)와 맞먹는 수준**까지 올라가서, policy gradient가 "이기는 것"과 "그냥 죽지 않고 돌아다니는 것"을 구분 못 함. Terminal ±50으로 키우고 shaping을 절반으로 낮춘 결과, per-episode shaping 예산 ~+120 max가 terminal 스윙(+50 − (−50) = 100)보다 작아졌어.

## Trainer 요청사항

1. **기존 체크포인트 폐기**: reward scale 자체가 변경되어 value function이 무효.
2. **Fresh PPO 학습**: `bot_level=1` 대상 500K 또는 1M steps 재학습 후 승률 비교.
3. **Metric 추적 권장**:
   - `info["consecutive_touches"]` 분포 — toss-loop 재발 여부 확인
   - `info["stalled_out"]` 비율 — stall penalty가 실제로 억제하는지
   - Episode length 분포 — 너무 짧으면 아직 공 못 넘김, 너무 길면 shaping farming
4. **Reward 분해 로깅 (optional)**: 학습 로그에 각 reward component를 분리해 기록하면 어떤 weight가 over/under 되는지 파악 가능. `_compute_reward`를 깨서 component별 dict 반환하는 식.

## Reference

- PR: [#40](https://github.com/shyoon-devops/pikachu-volleyball-rl/pull/40) feat(rl): rebalance reward weights
- Commit: `0f32235e`
- Prior anti-toss work (preserved): `f8ea6126`
- Physics parity port (earlier this session): `b0d0aaee`, `ab0151cd`, `47aa4ced`, `e5d765a0`

## 테스트 결과

- `tests/test_env.py`: 44/44 pass
- `tests/test_physics.py` + `tests/test_engine.py`: 56/56 pass (물리 엔진 무회귀)
- `tests/test_bot.py` + `tests/test_game_scenarios.py`: 71/71 pass
- Dev 컨테이너 health check: `HTTP 200`, mongo/disk/training/queues 모두 `ok`

---

**질문 / 이슈 있으면 AI Engineer로 연락.**
