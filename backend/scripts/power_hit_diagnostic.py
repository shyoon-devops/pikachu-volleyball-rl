"""Power-hit frequency diagnostic.

Runs N games at each bot level (1..5) and counts:
  - input_power_hit_frames: frames where either bot SENT power_hit=True
  - successful_power_hits: frames where ball.is_power_hit flipped to True
    (i.e. the power hit actually landed against the ball — input AND
    jumping AND a valid collision all aligned)

Also samples the RL discrete-action distribution by rolling a uniform
random policy through the env (we don't have a trained model guaranteed
on disk in CI, so uniform random is a sane floor).

Usage:
    python -m backend.scripts.power_hit_diagnostic [--games 100]

Writes a compact JSON report to stdout.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
import sys

# Make the repo root importable when run as a script from anywhere.
_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from backend.game.bot import RuleBasedBot  # noqa: E402
from backend.game.engine import PikachuVolleyball  # noqa: E402
from backend.rl.env import ACTION_MAP, PikachuVolleyballEnv  # noqa: E402


def _bot_vs_bot(level1: int, level2: int, games: int, max_frames: int = 3000) -> dict:
    """Run N bot-vs-bot matches and count power-hit events."""
    engine = PikachuVolleyball()
    bot1 = RuleBasedBot(level=level1)
    bot2 = RuleBasedBot(level=level2)

    p1_input_power = 0
    p2_input_power = 0
    ball_flag_raised = 0  # transitions False -> True on ball.is_power_hit
    total_frames = 0
    rounds_completed = 0

    for _ in range(games):
        state = engine.reset()
        prev_flag = False
        for _ in range(max_frames):
            a1 = bot1.get_action(state, is_player2=False)
            a2 = bot2.get_action(state, is_player2=True)
            if a1.power_hit:
                p1_input_power += 1
            if a2.power_hit:
                p2_input_power += 1
            state = engine.step(a1, a2)
            total_frames += 1
            if state.ball.is_power_hit and not prev_flag:
                ball_flag_raised += 1
            prev_flag = bool(state.ball.is_power_hit)
            if state.score1 >= 15 or state.score2 >= 15:
                rounds_completed += 1
                break

    return {
        "level1": level1,
        "level2": level2,
        "games": games,
        "total_frames": total_frames,
        "p1_input_power_hit_frames": p1_input_power,
        "p2_input_power_hit_frames": p2_input_power,
        "successful_power_hits": ball_flag_raised,
        "rounds_completed": rounds_completed,
        "successful_per_game": round(ball_flag_raised / max(1, games), 2),
        "input_rate_p1_per_1k_frames": round(
            1000 * p1_input_power / max(1, total_frames), 2
        ),
        "input_rate_p2_per_1k_frames": round(
            1000 * p2_input_power / max(1, total_frames), 2
        ),
    }


def _rl_action_distribution(episodes: int = 20, bot_level: int = 1) -> dict:
    """Sample the action space under a uniform-random policy.

    This gives us a baseline — if even the "random-policy lower bound"
    produces many power-hit collisions then the bot/RL architecture is
    fine and the issue is purely visual. If the floor is ~0 power-hit
    collisions, then the auto-power-hit gate in env.step() is too strict.
    """
    env = PikachuVolleyballEnv(bot_level=bot_level, max_steps=3000)
    import numpy as np

    rng = np.random.default_rng(42)
    counter: Counter[int] = Counter()
    successful = 0
    for _ in range(episodes):
        env.reset(seed=int(rng.integers(0, 1_000_000)))
        done = False
        prev_flag = False
        while not done:
            action = int(rng.integers(0, env.action_space.n))
            counter[action] += 1
            _, _, terminated, truncated, _ = env.step(action)
            ball = env._game._state.ball
            if ball.is_power_hit and not prev_flag:
                successful += 1
            prev_flag = bool(ball.is_power_hit)
            done = terminated or truncated
    # Power-hit actions are 6..11 per ACTION_MAP.
    power_actions = {k for k, v in ACTION_MAP.items() if v.power_hit}
    total = sum(counter.values())
    power_count = sum(c for a, c in counter.items() if a in power_actions)
    return {
        "episodes": episodes,
        "bot_level": bot_level,
        "total_actions": total,
        "power_action_count": power_count,
        "power_action_pct": round(100 * power_count / max(1, total), 2),
        "successful_power_hits": successful,
        "action_histogram": dict(sorted(counter.items())),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--games", type=int, default=100)
    parser.add_argument("--rl-episodes", type=int, default=20)
    args = parser.parse_args()

    report: dict = {"bot_vs_bot": [], "rl_random": None}

    # Symmetric self-play at each level so we isolate the effect of
    # level on power-hit frequency rather than confounding with match-up.
    for level in (1, 2, 3, 4, 5):
        report["bot_vs_bot"].append(_bot_vs_bot(level, level, args.games))

    report["rl_random"] = _rl_action_distribution(
        episodes=args.rl_episodes, bot_level=1
    )

    json.dump(report, sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
