"""Cross-environment evaluation report generator.

Queries dev/qa/prod MongoDB instances and produces a unified comparison report.

Usage:
    python -m backend.rl.eval_report                  # all envs
    python -m backend.rl.eval_report --env prod       # single env
    python -m backend.rl.eval_report --model 140000   # filter by checkpoint
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from datetime import datetime

import pymongo

# Environment connection config
ENV_CONFIG: dict[str, dict[str, str | int]] = {
    "dev": {"host": "localhost", "port": 27018, "db": "pikachu_rl_dev"},
    "qa": {"host": "localhost", "port": 27019, "db": "pikachu_rl_qa"},
    "prod": {"host": "localhost", "port": 27020, "db": "pikachu_rl_prod"},
}

# Pass/fail thresholds per level
THRESHOLDS: dict[int, dict[str, float]] = {
    1: {"win_rate": 0.90, "avg_score": 13.0, "avg_rally": 100.0},
    2: {"win_rate": 0.75, "avg_score": 11.0, "avg_rally": 80.0},
    3: {"win_rate": 0.50, "avg_score": 8.0, "avg_rally": 70.0},
    4: {"win_rate": 0.25, "avg_score": 5.0, "avg_rally": 60.0},
    5: {"win_rate": 0.10, "avg_score": 3.0, "avg_rally": 50.0},
}


@dataclass(frozen=True)
class EvalRecord:
    env: str
    model_path: str
    bot_level: int
    n_games: int
    win_rate: float
    avg_score: float
    avg_rally_length: float
    timestamp: str


def fetch_results(env_name: str, model_filter: str | None = None) -> list[EvalRecord]:
    """Fetch evaluation results from a specific environment's MongoDB."""
    cfg = ENV_CONFIG[env_name]
    try:
        client = pymongo.MongoClient(
            host=str(cfg["host"]), port=int(cfg["port"]), serverSelectionTimeoutMS=3000
        )
        db = client[str(cfg["db"])]
        query: dict = {}
        if model_filter:
            query["model_path"] = {"$regex": model_filter}
        cursor = db["evaluations"].find(query).sort("timestamp", -1).limit(100)
        records = []
        for doc in cursor:
            records.append(
                EvalRecord(
                    env=env_name,
                    model_path=doc.get("model_path", ""),
                    bot_level=doc.get("bot_level", 0),
                    n_games=doc.get("n_games", 0),
                    win_rate=doc.get("win_rate", 0.0),
                    avg_score=doc.get("avg_score", 0.0),
                    avg_rally_length=doc.get("avg_rally_length", 0.0),
                    timestamp=str(doc.get("timestamp", "")),
                )
            )
        client.close()
        return records
    except pymongo.errors.ServerSelectionTimeoutError:
        print(f"  [{env_name}] MongoDB unreachable — skipped", file=sys.stderr)
        return []


def verdict(level: int, win_rate: float) -> str:
    """Return pass/fail verdict for a single level."""
    threshold = THRESHOLDS.get(level, {}).get("win_rate", 1.0)
    if win_rate >= threshold:
        return "PASS"
    if level <= 3 and win_rate < 0.50:
        return "CRITICAL"
    return "FAIL"


def overall_verdict(records: list[EvalRecord]) -> str:
    """Determine overall model verdict from per-level results."""
    if not records:
        return "NO DATA"
    for r in records:
        v = verdict(r.bot_level, r.win_rate)
        if v == "CRITICAL":
            return "CRITICAL"
    for r in records:
        if r.bot_level <= 3 and verdict(r.bot_level, r.win_rate) == "FAIL":
            return "FAIL"
    l45_fail = any(
        verdict(r.bot_level, r.win_rate) == "FAIL" for r in records if r.bot_level >= 4
    )
    if l45_fail:
        return "CONDITIONAL"
    return "PASS"


def extract_checkpoint(model_path: str) -> str:
    """Extract checkpoint step number from model path."""
    parts = model_path.rstrip("/").split("/")
    name = parts[-1] if parts else model_path
    return name.replace(".zip", "")


def print_report(
    all_records: dict[str, list[EvalRecord]], model_filter: str | None = None
) -> None:
    """Print the unified cross-environment report."""
    title = "Evaluation Report"
    if model_filter:
        title += f" (filter: {model_filter})"
    print(f"\n{'=' * 72}")
    print(f"  {title}")
    print(f"  Generated: {datetime.now().astimezone().isoformat()}")
    print(f"{'=' * 72}\n")

    # Group by checkpoint
    checkpoints: dict[str, dict[str, list[EvalRecord]]] = {}
    for env_name, records in all_records.items():
        for r in records:
            cp = extract_checkpoint(r.model_path)
            checkpoints.setdefault(cp, {}).setdefault(env_name, []).append(r)

    if not checkpoints:
        print("  No evaluation data found.\n")
        return

    for cp, env_data in sorted(checkpoints.items()):
        print(f"  Checkpoint: {cp}")
        print(f"  {'─' * 66}")
        print(
            f"  {'Env':<6} {'Level':>5} {'Games':>5} "
            f"{'WinRate':>8} {'AvgScore':>9} {'AvgRally':>9} {'Verdict':>10}"
        )
        print(f"  {'─' * 66}")

        for env_name in ["dev", "qa", "prod"]:
            records = env_data.get(env_name, [])
            if not records:
                print(f"  {env_name:<6} {'—  no data —':>50}")
                continue
            for r in sorted(records, key=lambda x: x.bot_level):
                v = verdict(r.bot_level, r.win_rate)
                marker = " !!" if v in ("CRITICAL", "FAIL") else ""
                print(
                    f"  {r.env:<6} L{r.bot_level:>4} {r.n_games:>5} "
                    f"{r.win_rate:>7.0%} {r.avg_score:>9.1f} "
                    f"{r.avg_rally_length:>9.1f} {v:>10}{marker}"
                )

        # Overall per-env verdicts
        print(f"  {'─' * 66}")
        for env_name in ["dev", "qa", "prod"]:
            records = env_data.get(env_name, [])
            if records:
                ov = overall_verdict(records)
                print(f"  {env_name:<6} Overall: {ov}")
        print()

    # Threshold reference
    print(f"  {'─' * 66}")
    print("  Thresholds: L1≥90% L2≥75% L3≥50% L4≥25% L5≥10%")
    print(f"{'=' * 72}\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Cross-env evaluation report")
    parser.add_argument(
        "--env",
        choices=["dev", "qa", "prod"],
        help="Single environment (default: all)",
    )
    parser.add_argument("--model", help="Filter by checkpoint name substring")
    args = parser.parse_args()

    envs = [args.env] if args.env else ["dev", "qa", "prod"]
    all_records: dict[str, list[EvalRecord]] = {}
    for env_name in envs:
        print(f"  Fetching {env_name}...", file=sys.stderr)
        all_records[env_name] = fetch_results(env_name, model_filter=args.model)

    print_report(all_records, model_filter=args.model)


if __name__ == "__main__":
    main()
