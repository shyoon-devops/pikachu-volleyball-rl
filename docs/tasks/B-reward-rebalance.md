# Task B: Reward Shaping 재조정

**Requester:** Trainer (yoon/trainer)
**Assignee:** AI Engineer (yoon/ai-engineer)
**Priority:** P0 — 커리큘럼 진척 블로커
**Date:** 2026-04-12
**PM 승인:** ✅ (Option B, A/C 보류)

---

## 1. 근거 데이터 — 500K 훈련 결과

**Experiment:** `ppo_anti_toss_20260412_152041`
**Commit:** `96be767e` (dev + f8ea6126 anti-toss-loop)
**Config:** L1 bot, 500K steps, seed=42, default hyperparams, 8 envs

### 1.1 핵심 이상 신호: mean_reward ↗ vs win_rate ━

| Step | Win rate | Mean reward |
|---|---|---|
| 40K  | 28.6% | 176.97 |
| 100K | 16.7% | 182.26 |
| 200K | 26.2% | 192.30 |
| 300K | — | — |
| 500K | **28.0%** | **207.58** |

**Δ:** mean_reward **+17.3%** ↗, win_rate **-0.6pp** ━

> **진단:** 에이전트가 보상 셰이핑 이벤트(공 터치, 네트 크로싱, approach-ball gradient)는 성공적으로 수확하지만, **실제 게임 승리로 전환되지 않음**. 전형적인 **reward hacking / shaping farming** 패턴.

### 1.2 보상 크기 시뮬레이션 (1게임당, 15점 기준)

현재 `backend/rl/env.py:231-310` 분석:

| 카테고리 | 게임당 대략 합 | 비고 |
|---|---|---|
| Primary: 점수 이벤트 (±10×15) | ±150 | 승리 확정 |
| Primary: 게임 종료 (±20) | ±20 | |
| Aux: 터치 (+3/+1/-2) | +5 ~ +30 | |
| Aux: 네트 크로싱 (+2) | +10 ~ +30 | |
| **Aux: approach-ball (+0.05/frame 연속)** | **+25 ~ +100** | **문제: cumulative가 primary와 비슷한 규모** |
| Aux: ready position (+0.01/frame 연속) | +5 ~ +30 | 위와 동일 |
| Aux: stall penalty (-0.03/frame after 300f) | 0 ~ -30 | |

**문제점:**
- **Continuous aux (approach/ready)의 cumulative가 primary 신호와 비등한 규모**
- 0-15로 지는 경기에서도 aux shaping만 +60 이상 받을 수 있음
- 15-0 승리 vs 0-15 패배의 reward 차이가 expected ±300이 아니라 사실상 ±150 수준으로 희석
- → 그래디언트가 **shaping 수확 정책**에 수렴, 승리 학습 유인 부족

---

## 2. 물리 엔진 변경과의 상호작용 (중요)

AI Engineer가 `yoon/ai-engineer` 브랜치에서 작업한 최근 커밋:

| Commit | 요약 | Reward 영향 |
|---|---|---|
| `b0d0aaee` | fix: port game engine faithfully to gorisanson/pikachu-volleyball original | ⚠️ ball.vy/vx 업데이트 경로 변경 → 터치 검출 조건 브리틀 |
| `e5d765a0` | fix: gate ball-player collision with isCollisionWithBallHappened flag | ⚠️ 충돌 1회 후 같은 프레임 재충돌 차단 → 기존 `ball.vy <= -14` 휴리스틱과 충돌 가능 |
| `47aa4ced` | test: rework tests affected by faithful physics port | 테스트만 |
| `ab0151cd` | test: add physics regression suite | 테스트만 |

**현재 상태:** 이 4개 커밋은 **dev에 미머지**. 500K 훈련은 **구 물리 엔진** 기반.

**Reward 재조정 전 반드시 확인해야 할 것:**
- 현재 `env.py` 터치 검출 (`self._prev_ball_vy >= 0 and ball.vy <= -14`)이 faithful physics에서도 올바르게 trigger되는가?
- `NET_CROSSING_REWARD` 검출 (`ball.vx > 0` + x 경계 교차)이 충돌 게이트 이후에도 정확한가?

---

## 3. 요청 사항

### 3.1 물리 엔진 선행 머지
- **먼저** `yoon/ai-engineer` 브랜치의 b0d0aaee/e5d765a0 포함 physics 커밋들을 **dev에 머지**.
- 이후 trainer가 pull하여 새 reward 설계 기반 수립.

### 3.2 Reward Shaping 재설계

핵심 원칙 3가지:

**원칙 1: Primary signal이 shaping보다 1 order of magnitude 크게 유지**
- Win/loss signal을 ±20 → ±50 또는 ±100으로 증폭 검토
- 점수 이벤트 ±10은 유지 (누적 ±150으로 충분)
- **aux cumulative 총합이 ±50을 넘지 않도록 scale 조정**

**원칙 2: Continuous aux는 potential-based로 전환**
- 현재 approach-ball (+0.05/frame)은 non-potential shaping → optimal policy invariance 보장 없음 (Ng et al. 1999)
- Potential-based shaping으로 재작성: `F(s,s') = γ·Φ(s') - Φ(s)` 형태
- 예: `Φ(s) = -|ball.x - p1.x|/GROUND_WIDTH` — 공에 가까우면 potential 높음, 멀어지면 낮음
- 이렇게 하면 cumulative가 0에 수렴 → optimal policy 훼손 없이 학습 가속

**원칙 3: 터치/크로싱 검출은 물리 엔진 신뢰 가능한 signal 사용**
- `ball.vy <= -14` 같은 휴리스틱 대신, engine에서 직접 `ball.is_player_hit_this_frame` 같은 plain signal을 내보내도록 검토 (엔진 수정 범위)
- Net crossing도 `ball.crossed_net_this_frame` 등 explicit flag 고려

### 3.3 검증 지침
- `backend/tests/test_env.py` 에 reward 회귀 테스트 추가: 특정 상태 시퀀스에 대한 reward 값 pin
- `backend/tests/test_physics.py` (AI Engineer가 ab0151cd에서 추가) 와 충돌 없도록 조정

---

## 4. 참고 문헌 (Reward Shaping Best Practices)

1. **Ng, Harada, Russell (1999)** — *"Policy Invariance Under Reward Transformations: Theory and Application to Reward Shaping"*, ICML 1999
   핵심: Potential-based reward shaping(PBRS)만이 optimal policy 보존. `F(s,s') = γΦ(s') - Φ(s)` 형태.
   → 적용: approach-ball, ready-position을 PBRS로 재작성.

2. **OpenAI (2019)** — *"Dota 2 with Large Scale Deep Reinforcement Learning"*, arXiv:1912.06680
   핵심: primary reward가 shaping보다 최소 10배 크게 유지 + shaping은 **teamwork / short-term credit assignment** 용도에만.
   → 적용: aux cumulative ≤ primary / 10 rule.

3. **Vinyals et al. (2019)** — *"Grandmaster level in StarCraft II using multi-agent reinforcement learning"*, Nature
   핵심: reward clipping + league training로 shaping farming 방지.
   → 적용: episode당 aux reward에 hard cap 씌우기 (e.g. `+30` 상한).

4. **SB3 공식 문서** — [Custom Environment 가이드](https://stable-baselines3.readthedocs.io/en/master/guide/custom_env.html)
   핵심: reward scale이 log prob 스케일과 상호작용. value loss 폭주 시 reward 재조정 필요.
   → 현재 PPO hyperparam 유지 가정 하에 reward magnitude 조정만으로 해결 시도.

---

## 5. 산출물 계약 (Deliverable)

AI Engineer 구현 후 commit 구조:

```
yoon/ai-engineer:
  [optional] merge to dev first: faithful physics + collision gate
  feat(reward): potential-based shaping + scale rebalance
  test(env): add reward regression pins for key state sequences
```

완료 신호:
- AI Engineer가 `yoon/ai-engineer` 브랜치에 푸시 → Trainer(나)가 pull & validate
- 혹은 dev 머지 완료 → trainer 브랜치에서 `git merge github/dev`

---

## 6. 검증 계획 (Trainer 측)

AI Engineer 커밋 pull 후:

1. **100K steps 짧은 검증 훈련** — L1 bot, seed=42, 같은 hyperparams
2. **판정 기준 (B 완료 조건):**
   - Win rate **≥ 40%** at 100K (현재 20% 수준 대비 2배)
   - Mean reward divergence 해소 — reward 상승률과 win rate 상승률이 같은 방향성
3. **B 통과 시 자동으로 Option A 실행** — 500K → 2M 장기 훈련

---

## 7. 문의

이 요청에 대한 질문/우려/대안은:
- PM에게 comment
- 또는 `yoon/ai-engineer` 브랜치에서 직접 반박 커밋으로 응답

감사합니다. 빠른 협업 부탁드립니다.

— Trainer
