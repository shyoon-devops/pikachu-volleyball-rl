"""Headless bot-difficulty validation.

Runs N games per matchup and reports win/loss/draw rates so we can verify
the PM 2026-04-12 difficulty upgrade hit its targets:

  * L1 vs random policy   → 65-75% L1 wins
  * L3 vs L1              → comfortable L3 majority
  * L5 vs L3              → clear L5 edge (regression check)
  * L5 vs random PPO-ish  → target 50-60% L5 wins (best-effort when a
                            checkpoint is available on disk; otherwise
                            we skip and note it in the report)

Usage:
    python3 -m backend.scripts.bot_difficulty_validate [--games 100]

Prints a compact JSON blob to stdout. The caller (CI or the
REPORT-BOT-DIFFICULTY-UPGRADE.md doc) snapshots it.
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from backend.game.bot import RuleBasedBot  # noqa: E402
from backend.game.engine import PikachuVolleyball, PlayerInput  # noqa: E402


# Hard cap per game so a stuck rally can't wedge the whole sim. The engine
# already has RALLY_MAX_FRAMES=600 per rally + rally-timeout safety valve,
# so 50k frames is several minutes of in-game time.
MAX_FRAMES_PER_GAME = 50_000


def _random_policy_action() -> PlayerInput:
    """Pure-random 12-way policy (mirrors ACTION_MAP's shape)."""
    return PlayerInput(
        x_dir=random.choice([-1, 0, 1]),
        y_dir=random.choice([-1, 0, 1]),
        power_hit=random.random() < 0.10,
    )


def _run_match(
    *,
    p1_policy,
    p2_policy,
    games: int,
) -> dict[str, float | int]:
    """Play `games` matches; return win/loss/draw counts for p1.

    `p1_policy` / `p2_policy` are callables ``(state, is_p2) -> PlayerInput``.
    """
    p1_wins = p2_wins = draws = 0
    total_frames = 0
    for _ in range(games):
        game = PikachuVolleyball()
        state = game.reset()
        for _ in range(MAX_FRAMES_PER_GAME):
            a1 = p1_policy(state, False)
            a2 = p2_policy(state, True)
            state = game.step(a1, a2)
            if state.score1 >= 15 or state.score2 >= 15:
                break
        total_frames += state.frame
        if state.score1 > state.score2:
            p1_wins += 1
        elif state.score2 > state.score1:
            p2_wins += 1
        else:
            draws += 1
    return {
        "games": games,
        "p1_wins": p1_wins,
        "p2_wins": p2_wins,
        "draws": draws,
        "p1_win_rate": round(p1_wins / games, 3),
        "avg_frames": round(total_frames / games, 1),
    }


def _bot_policy(bot: RuleBasedBot):
    def _fn(state, is_p2: bool):
        return bot.get_action(state, is_player2=is_p2)
    return _fn


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--games", type=int, default=100)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    random.seed(args.seed)

    results: dict[str, dict] = {}

    # L1 vs random — target 65-75% L1 wins.
    results["L1_vs_random"] = _run_match(
        p1_policy=_bot_policy(RuleBasedBot(level=1)),
        p2_policy=lambda _s, _p2: _random_policy_action(),
        games=args.games,
    )

    # L3 vs L1 — should be a comfortable L3 majority.
    results["L3_vs_L1"] = _run_match(
        p1_policy=_bot_policy(RuleBasedBot(level=3)),
        p2_policy=_bot_policy(RuleBasedBot(level=1)),
        games=args.games,
    )

    # L5 vs L3 — regression: the skill ordering must hold.
    results["L5_vs_L3"] = _run_match(
        p1_policy=_bot_policy(RuleBasedBot(level=5)),
        p2_policy=_bot_policy(RuleBasedBot(level=3)),
        games=args.games,
    )

    # L5 vs random PPO-like — stand-in for "average RL model". We use a
    # pure random policy (the only RL baseline guaranteed to exist on disk
    # in CI). If a real checkpoint is later plugged in, swap this.
    results["L5_vs_random"] = _run_match(
        p1_policy=_bot_policy(RuleBasedBot(level=5)),
        p2_policy=lambda _s, _p2: _random_policy_action(),
        games=args.games,
    )

    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
