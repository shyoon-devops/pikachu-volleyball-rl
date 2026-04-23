"""Ad-hoc driver: run bench-B final (2M) eval across L1/L3/L5 × 5 seeds.

Writes raw per-eval results + aggregated 95% Wilson CIs to a JSON next to
this file. Intentionally not a committed module — this is a scratch
runner for the 2026-04-23 bench-B evaluation pass.
"""

from __future__ import annotations

import json
import math
import sys
import time
from collections import defaultdict
from dataclasses import asdict
from pathlib import Path

from backend.rl.batch_evaluate import run_batch

CKPT = (
    "/home/yoon/.claude-squad/worktrees/bench/v200-dreamer/models/bench/B/"
    "3cb6ffd9-7d49-4906-8f16-83ec43f534a2/bench-B__3cb6ffd9__final.zip"
)
LEVELS = (1, 3, 5)
SEEDS = (101, 102, 103, 104, 105)
N_GAMES = 100
ALGORITHM = "dreamer_v3"
WORKERS = 5


def wilson_ci(wins: int, trials: int, z: float = 1.96) -> tuple[float, float]:
    if trials == 0:
        return 0.0, 0.0
    p = wins / trials
    denom = 1.0 + z * z / trials
    centre = (p + z * z / (2.0 * trials)) / denom
    half = z * math.sqrt(p * (1.0 - p) / trials + z * z / (4.0 * trials * trials)) / denom
    return centre - half, centre + half


def main() -> int:
    t0 = time.time()
    report = run_batch(
        [CKPT],
        levels=list(LEVELS),
        n_games=N_GAMES,
        workers=WORKERS,
        seeds=list(SEEDS),
        algorithm=ALGORITHM,
    )
    elapsed = time.time() - t0

    per_level: dict[int, list[dict]] = defaultdict(list)
    for r in report.results:
        per_level[r.bot_level].append(
            {
                "seed": getattr(r, "seed", None),
                "n_games": r.n_games,
                "win_rate": r.win_rate,
                "wins": int(round(r.win_rate * r.n_games)),
                "avg_score": r.avg_score,
                "avg_opp_score": r.avg_opponent_score,
                "avg_rally": r.avg_rally_length,
                "dominance": r.dominance_score,
            }
        )

    agg: dict[int, dict] = {}
    for level, rows in per_level.items():
        total_wins = sum(r["wins"] for r in rows)
        total_trials = sum(r["n_games"] for r in rows)
        p = total_wins / total_trials if total_trials else 0.0
        lo, hi = wilson_ci(total_wins, total_trials)
        agg[level] = {
            "wins": total_wins,
            "trials": total_trials,
            "win_rate": p,
            "ci95_low": lo,
            "ci95_high": hi,
            "n_seeds": len(rows),
            "avg_rally_mean": sum(r["avg_rally"] for r in rows) / len(rows),
            "dominance_mean": sum(r["dominance"] for r in rows) / len(rows),
        }

    out = {
        "checkpoint": CKPT,
        "algorithm": ALGORITHM,
        "step": 2_000_000,
        "seeds": list(SEEDS),
        "levels": list(LEVELS),
        "n_games_per_seed": N_GAMES,
        "workers": WORKERS,
        "elapsed_seconds": elapsed,
        "failures": [asdict(f) for f in report.failures],
        "per_level_per_seed": {str(k): v for k, v in per_level.items()},
        "aggregated": {str(k): v for k, v in agg.items()},
    }

    out_path = Path(__file__).parent / "_bench_b_final_2M.json"
    out_path.write_text(json.dumps(out, indent=2, sort_keys=True))
    print(f"Wrote {out_path} (elapsed={elapsed:.0f}s, failures={len(report.failures)})")
    return 0 if not report.failures else 2


if __name__ == "__main__":
    sys.exit(main())
