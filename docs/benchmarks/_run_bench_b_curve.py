"""Ad-hoc driver: bench-B sample-efficiency curve (100k / 500k / 1M / 1.5M / 2M).

Reuses `_bench_b_final_2M.json` for the 2M point (already produced 2026-04-23)
and evaluates the 4 earlier checkpoints fresh. Emits combined JSON and a
matplotlib PNG of step vs winrate, one line per bot level.

Scratch runner — not intended to land in backend/. Same style as
`_run_bench_b_final.py`.
"""

from __future__ import annotations

import json
import math
import sys
import time
from collections import defaultdict
from dataclasses import asdict
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from backend.rl.batch_evaluate import run_batch

CKPT_DIR = Path(
    "/home/yoon/.claude-squad/worktrees/bench/v200-dreamer/models/bench/B/"
    "3cb6ffd9-7d49-4906-8f16-83ec43f534a2"
)
CURVE_STEPS_TO_EVAL = (100_000, 500_000, 1_000_000, 1_500_000)
CURVE_STEPS_ALL = (100_000, 500_000, 1_000_000, 1_500_000, 2_000_000)
LEVELS = (1, 3, 5)
SEEDS = (101, 102, 103, 104, 105)
N_GAMES = 100
ALGORITHM = "dreamer_v3"
WORKERS = 5

HERE = Path(__file__).parent
FINAL_JSON = HERE / "_bench_b_final_2M.json"
CURVE_JSON = HERE / "_bench_b_curve.json"
CURVE_PNG = HERE / "v200-bench-b-curve.png"


def wilson_ci(wins: int, trials: int, z: float = 1.96) -> tuple[float, float]:
    if trials == 0:
        return 0.0, 0.0
    p = wins / trials
    denom = 1.0 + z * z / trials
    centre = (p + z * z / (2.0 * trials)) / denom
    half = z * math.sqrt(
        p * (1.0 - p) / trials + z * z / (4.0 * trials * trials)
    ) / denom
    return centre - half, centre + half


def _ckpt_path(step: int) -> str:
    return str(CKPT_DIR / f"bench-B__3cb6ffd9__{step}.zip")


def _aggregate(per_level_rows: dict[int, list[dict]]) -> dict[int, dict]:
    agg: dict[int, dict] = {}
    for level, rows in per_level_rows.items():
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
    return agg


def eval_one_step(step: int) -> dict:
    ckpt = _ckpt_path(step)
    t0 = time.time()
    report = run_batch(
        [ckpt],
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
                "avg_rally": r.avg_rally_length,
                "dominance": r.dominance_score,
            }
        )
    return {
        "step": step,
        "checkpoint": ckpt,
        "elapsed_seconds": elapsed,
        "failures": [asdict(f) for f in report.failures],
        "per_level_per_seed": {str(k): v for k, v in per_level.items()},
        "aggregated": {str(k): v for k, v in _aggregate(per_level).items()},
    }


def load_final_2M() -> dict:
    raw = json.loads(FINAL_JSON.read_text())
    return {
        "step": 2_000_000,
        "checkpoint": raw["checkpoint"],
        "elapsed_seconds": raw["elapsed_seconds"],
        "failures": raw["failures"],
        "per_level_per_seed": raw["per_level_per_seed"],
        "aggregated": raw["aggregated"],
    }


def plot_curve(points: list[dict]) -> None:
    points_sorted = sorted(points, key=lambda p: p["step"])
    steps = [p["step"] / 1_000_000 for p in points_sorted]

    fig, ax = plt.subplots(figsize=(8.5, 5.2), dpi=120)
    colours = {"1": "#1f77b4", "3": "#d62728", "5": "#2ca02c"}
    markers = {"1": "o", "3": "s", "5": "^"}
    for level in ("1", "3", "5"):
        wr = [p["aggregated"][level]["win_rate"] for p in points_sorted]
        lo = [p["aggregated"][level]["ci95_low"] for p in points_sorted]
        hi = [p["aggregated"][level]["ci95_high"] for p in points_sorted]
        errs_low = [wr[i] - lo[i] for i in range(len(wr))]
        errs_high = [hi[i] - wr[i] for i in range(len(wr))]
        ax.errorbar(
            steps, wr,
            yerr=[errs_low, errs_high],
            marker=markers[level], capsize=3, linewidth=1.8, markersize=7,
            color=colours[level], label=f"L{level}",
        )

    # PPO §9 reference line at 0.62 (ADR 0016 §1 plateau)
    ax.axhline(0.62, color="#888", linestyle="--", linewidth=1,
               label="PPO shaped_v1 L3 plateau (ADR 0016 §1, 0.62)")

    ax.set_xlabel("Training step (M)")
    ax.set_ylabel("Winrate (500 trials / point; 95% Wilson CI)")
    ax.set_title("bench-B Dreamer V3 sample-efficiency curve vs rule-based bot")
    ax.set_xticks([0.1, 0.5, 1.0, 1.5, 2.0])
    ax.set_xlim(0, 2.1)
    ax.set_ylim(-0.02, 1.02)
    ax.grid(True, alpha=0.3)
    ax.legend(loc="center right", fontsize=9)

    fig.tight_layout()
    fig.savefig(CURVE_PNG)
    print(f"Wrote {CURVE_PNG}")


def main() -> int:
    t0 = time.time()
    results: list[dict] = [load_final_2M()]
    for step in CURVE_STEPS_TO_EVAL:
        print(f"Evaluating step {step}...", flush=True)
        results.append(eval_one_step(step))

    # Sort by step and emit combined JSON
    results.sort(key=lambda r: r["step"])
    out = {
        "checkpoints_evaluated": list(CURVE_STEPS_ALL),
        "seeds": list(SEEDS),
        "levels": list(LEVELS),
        "n_games_per_seed": N_GAMES,
        "algorithm": ALGORITHM,
        "workers": WORKERS,
        "total_elapsed_seconds": time.time() - t0,
        "points": results,
    }
    CURVE_JSON.write_text(json.dumps(out, indent=2, sort_keys=True))
    print(f"Wrote {CURVE_JSON}")

    plot_curve(results)

    # Console summary
    print("\n--- Curve summary ---")
    print(f"{'step':>10} | {'L1':>6} {'L1 CI':>14} | {'L3':>6} {'L3 CI':>14} | {'L5':>6} {'L5 CI':>14}")
    for p in results:
        a = p["aggregated"]
        row = f"{p['step']:>10} |"
        for lvl in ("1", "3", "5"):
            wr = a[lvl]["win_rate"]
            lo = a[lvl]["ci95_low"]
            hi = a[lvl]["ci95_high"]
            row += f" {wr*100:>5.1f}% [{lo*100:>4.1f},{hi*100:>5.1f}] |"
        print(row)
    total_fail = sum(len(p["failures"]) for p in results)
    print(f"Total failures across curve: {total_fail}")
    return 0 if total_fail == 0 else 2


if __name__ == "__main__":
    sys.exit(main())
