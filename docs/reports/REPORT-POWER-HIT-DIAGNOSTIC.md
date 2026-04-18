# Power-Hit Diagnostic Report

**Date:** 2026-04-12
**Author:** AI Engineer
**Triggered by:** User feedback via PM — "대시보드 계속 보는데 한 번도 강타 쓰는 거 못 봤다"
**Related hotfix:** backend exposure of `ball.is_power_hit` (this commit)
**Follow-up owner:** Frontend (GameCanvas hyper-ball / trail rendering)

## TL;DR

Bots and the RL action space DO use power hit — frequently. The user
cannot see it because the frontend uses a fragile speed-based heuristic
that misses many valid power hits. Backend now exposes the authoritative
`ball.is_power_hit` flag so FE can stop guessing.

## Methodology

Ran `backend/scripts/power_hit_diagnostic.py` with `--games 100
--rl-episodes 10`:

1. **Bot-vs-bot self-play** at every level 1–5 (100 games each).
   Counted: `power_hit=True` input frames per side + ball-flag rising
   edges (the authoritative "this was actually a power-hit collision"
   signal).
2. **RL action distribution under uniform-random policy** against a L1
   bot (10 episodes). Counted: per-action histogram, fraction of
   power-hit actions (6–11), and successful power-hit collisions.

Uniform-random was used for the RL side because a trained model is not
guaranteed in CI; it represents the floor. A trained policy can only be
higher or equal (up to the collision gate).

## Bot-vs-bot results (100 games each)

| Level | Successful power hits / game | P1 input rate / 1000 frames | Rounds completed / 100 |
| ----- | ---------------------------- | --------------------------- | ---------------------- |
| L1    | **13.72**                    | 47.91                       | 61                     |
| L2    | **31.29**                    | 119.82                      | 13                     |
| L3    | **33.33**                    | 198.16                      | 94                     |
| L4    | **32.99**                    | 293.82                      | 100                    |
| L5    | **26.65**                    | 361.62                      | 100                    |

Interpretation:

- Even at L1 the bot lands **~14 power hits per game**. The user would
  see roughly one every few seconds *if the FE rendered them*.
- L3–L5 land ~27–33 power hits per game.
- L2 shows low `rounds_completed` = 13 because L2's stochastic
  hesitation can stall rallies that the rally-timeout (600 frames)
  truncates; raw successful_power_hits is still high, only rounds are
  incomplete.
- L5 successful-rate drops vs L3/L4 because rallies are much shorter —
  more points finish in a single exchange (shortest total_frames:
  117K vs L3's 230K), so there are physically fewer hit opportunities.

**Conclusion for bots:** no gameplay gap. Do NOT relax the bot's
collision conditions — they are already firing plenty of power hits.

## RL (uniform-random policy, 10 episodes vs L1)

- Total actions sampled: 21,704
- Actions 6–11 (power-hit actions) chosen: **10,786 (49.7 %)**
- Successful power-hit collisions: **189** (~18.9 / episode)
- Action histogram is flat within ±4 % across all 12 actions — sampler
  is unbiased.

The uniform-random floor already achieves ~19 successful power hits per
episode. A trained PPO policy will only match or exceed this (subject
to whether the shaped reward discourages them, which currently it does
not).

## Why the user cannot see them

`frontend/src/components/game/GameCanvas.tsx:27-28`:

```tsx
// Power-hit detection threshold (heuristic — backend doesn't send isPowerHit)
const POWER_HIT_SPEED = 25
```

The FE infers power hits from ball speed alone. Looking at the formula
the engine uses (original `physics.js:711`):

```
vx = ±(|xDir| + 1) * 10   →  10 or 20 depending on xDir
vy = |vy_in| * yDir * 2   →  0 if yDir==0, else ≥ 30
```

The failure modes of the heuristic:

- `xDir=1, yDir=0` power hit → `speed = sqrt(20² + 0²) = 20`. **Below
  threshold 25 — rendered as a normal hit.**
- `xDir=0, yDir=±1` power hit → `speed ≥ sqrt(10² + 30²) = 31.6`.
  Rendered correctly.
- `xDir=0, yDir=0` power hit → `speed = 10`. **Far below threshold.**
- Incoming ball with residual speed > 25 from a previous hit → rendered
  as "power" even though nothing happened this frame (false positive).

So a meaningful fraction of genuine power hits — especially flat
horizontal smashes, which are the most visually satisfying ones — are
being rendered as plain hits. That matches the user's observation.

## Fix landed in this commit (backend)

- `BallState.is_power_hit: bool` added (defaults to `False`).
- `_check_ball_player_collision` sets it true on the power-hit branch
  and false on the non-power-hit branch, matching
  `physics.js:725/727` exactly.
- `_serialize_state` includes it in the WS frame payload as
  `ball.is_power_hit`.
- `replay_service._BALL_DEFAULTS` back-fills it to `False` for legacy
  replays.
- 4 regression tests in `TestBallIsPowerHitFlag` pin the behaviour.

## Action required — Frontend

Replace the speed heuristic with the authoritative flag:

```tsx
// BEFORE
const ballSpeed = Math.sqrt(state.ball.vx ** 2 + state.ball.vy ** 2)
const isPowerHit = ballSpeed > POWER_HIT_SPEED

// AFTER
const isPowerHit = state.ball.isPowerHit ?? false
```

Plus:

1. Add `isPowerHit?: boolean` to the ball shape in
   `frontend/src/lib/types.ts`.
2. Pass it through `lerpState` (boolean snap, not lerp — take `next`).
3. Delete the now-dead `POWER_HIT_SPEED` constant.
4. Optional: add a short 3-frame fade-out on the hyper/trail sprites so
   the effect doesn't disappear instantly when the flag clears on the
   next opposing hit.

## Repro

```
python -m backend.scripts.power_hit_diagnostic --games 100 --rl-episodes 10
```

Script is deterministic modulo bot stochastic knobs; ranges above are
representative.
