# Follow-up — L3>L4 ordering regression in post-port bot ladder

**Author:** AI Engineer
**Date:** 2026-04-13
**Priority:** P2 (tuning quality, not correctness)
**Scope:** `backend/game/bot.py::BOT_PARAMS` levels 2–4

---

## What this notice is not

This is NOT the L5<L3 regression — that was the PM-scoped fix and is
resolved by commit ``fix(bot): L5 difficulty regression after physics
port`` (L5's ``jump_timing_error`` 0 → -1).

## What this notice IS

While measuring the full L1-vs-L1..L5 ladder after the L5 fix, the
following ordering issues were observed under the new ported physics:

| Matchup | Higher-level wins |
|---|---|
| L1 vs L2 | 13/15 ✓ |
| L2 vs L3 | 7/15 (flat — below majority) |
| **L3 vs L4** | **2/15 ✗ (inverted — L3 dominates L4)** |
| L4 vs L5 | 15/15 ✓ |
| L1 vs L3 | 12/15 ✓ |
| L1 vs L4 | 12/15 ✓ |
| **L2 vs L4** | **5/15 ✗ (inverted — L2 beats L4)** |
| L1 vs L5 | 15/15 ✓ |
| L2 vs L5 | 14/15 ✓ |
| L3 vs L5 | 15/15 ✓ (post-fix) |

Seed bases tested: 1000, 2000, 3000, 4000. Pattern is consistent,
not a statistical fluke.

## Probable cause

The physics port introduced three dynamics that reward late-commit
aggression and punish early-commit intercepts:

1. **state=2 power-hit dwell (10 frames)** — jumping too early burns
   the state=2 slot before the ball arrives; late jumpers land
   inside the dwell window and reliably trigger power hits.
2. **Zero-vx rand() tiebreak** — adds small stochastic kick on
   perfectly-aligned intercepts. Precise bots suffer more than
   noisy bots here because precise bots position for exact alignment.
3. **Unconditional gravity** — subtle edge-case changes in landing
   frames that interact with the dwell window above.

L3's noise profile (jump_jitter=2, hesitation_rate=0.05) happens to
land its commits later than L4's, which is why L3 outplays L4
post-port. This is a case of physics-change invalidating a static
parameter fit.

## Out of scope for the L5 fix commit because…

- PM scoped that commit to "L5 > L3".
- Tuning L4 without re-tuning L2/L3 risks chain regressions
  (fixing L4 might break L4-vs-L2, which is already inverted at
  5/15).
- Stabilising the full ladder is a multi-parameter search — not a
  two-line bump. It should either:
  (a) adopt a search-driven fit (evolutionary / Bayesian opt over
      the 9-knob BOT_PARAMS for all 5 levels simultaneously), or
  (b) be deferred until after the RL checkpoint re-run completes,
      when the post-port "ground truth" of skill levels becomes
      visible from PPO training curves.

## Suggested follow-up path

1. Wait for Trainer's post-port PPO re-train (PM approved it
   alongside the physics port). Capture per-level win curves against
   the RL agent.
2. Choose L2/L3/L4 targets against the re-trained RL agent so the
   tuning matches the RL env's actual difficulty curve rather than
   inter-bot ordering.
3. Do the tuning in a dedicated commit `fix(bot): restore L2–L4
   ladder ordering post-physics-port` with a measurement table in
   the commit message.

## Measurement script reference

The matchup numbers above came from the probe pattern used in the
L5 tuning session:

```python
def eval_matchup(lo, hi, n_games=15, seed_base=1000):
    import random as rng
    rng.seed(42)
    from backend.game.engine import PikachuVolleyball
    from backend.game.bot import RuleBasedBot
    hi_wins = 0
    for i in range(n_games):
        game = PikachuVolleyball(seed=seed_base + i)
        state = game.reset()
        lo_bot = RuleBasedBot(level=lo)
        hi_bot = RuleBasedBot(level=hi)
        for _ in range(50000):
            a1 = lo_bot.get_action(state, is_player2=False)
            a2 = hi_bot.get_action(state, is_player2=True)
            state = game.step(a1, a2)
            if state.score1 >= 15 or state.score2 >= 15:
                break
        if state.score2 > state.score1:
            hi_wins += 1
    return hi_wins
```

This block (or a cleaner derivative) belongs in a dedicated probe
script once the followup commit lands; reproducing the numbers
before proposing knob changes is essential.

---
**end of notice.**
