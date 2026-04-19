"""Aggregate freeze-smoke CSV output into event-level statistics.

Reads $FREEZE_DIAG_FILE (default /tmp/freeze.csv) and prints:
- per-event: count, mean, p50, p95, max (ms)
- inter-call gaps for env.step per env_index (freeze detector)
- gradient-update window (rollout.end → rollout.start) duration.
- recommended fixes based on which bucket dominates the tail.
"""

from __future__ import annotations

import os
import statistics
from collections import defaultdict
from pathlib import Path


def main() -> None:
    path = Path(os.environ.get("FREEZE_DIAG_FILE", "/tmp/freeze.csv"))
    if not path.exists():
        print(f"no CSV at {path}")
        return

    events_by_name: dict[str, list[float]] = defaultdict(list)
    env_step_timestamps: dict[int, list[float]] = defaultdict(list)
    rollout_boundaries: list[tuple[float, str]] = []

    with path.open() as f:
        header = f.readline()
        if not header.strip().startswith("ts_ms"):
            raise RuntimeError(f"unexpected header: {header!r}")
        for line in f:
            parts = line.rstrip().split(",")
            if len(parts) < 5:
                continue
            ts_ms, event, env_idx_s, dur_s, _extra = parts[:5]
            ts = float(ts_ms)
            if dur_s:
                events_by_name[event].append(float(dur_s))
            if event == "env.step":
                env_step_timestamps[int(env_idx_s)].append(ts)
            if event.startswith("rollout."):
                rollout_boundaries.append((ts, event))

    print("── per-event timings (ms) ───────────────────────────────────")
    print(
        f"{'event':<30}{'count':>8}{'mean':>10}{'p50':>10}"
        f"{'p95':>10}{'max':>10}"
    )
    for name in sorted(events_by_name):
        xs = events_by_name[name]
        if not xs:
            continue
        mean = statistics.mean(xs)
        p50 = statistics.median(xs)
        xs_sorted = sorted(xs)
        p95 = xs_sorted[int(0.95 * (len(xs_sorted) - 1))]
        mx = max(xs)
        print(
            f"{name:<30}{len(xs):>8}{mean:>10.2f}{p50:>10.2f}"
            f"{p95:>10.2f}{mx:>10.2f}"
        )

    # Gap analysis: time between consecutive env.step calls per env.
    print("\n── env.step inter-call gaps (ms) ────────────────────────────")
    all_gaps: list[float] = []
    for env_idx, ts_list in sorted(env_step_timestamps.items()):
        if len(ts_list) < 2:
            continue
        ts_sorted = sorted(ts_list)
        gaps = [
            ts_sorted[i + 1] - ts_sorted[i]
            for i in range(len(ts_sorted) - 1)
        ]
        all_gaps.extend(gaps)
        if gaps:
            sg = sorted(gaps)
            p95 = sg[int(0.95 * (len(sg) - 1))]
            print(
                f"  env {env_idx}: n={len(gaps)} "
                f"mean={statistics.mean(gaps):.2f} "
                f"p95={p95:.2f} max={max(gaps):.2f}"
            )
    if all_gaps:
        sg = sorted(all_gaps)
        p50 = statistics.median(all_gaps)
        p95 = sg[int(0.95 * (len(sg) - 1))]
        p99 = sg[int(0.99 * (len(sg) - 1))]
        mx = max(all_gaps)
        over_100 = sum(1 for g in all_gaps if g > 100.0)
        over_500 = sum(1 for g in all_gaps if g > 500.0)
        over_1500 = sum(1 for g in all_gaps if g > 1500.0)
        print(
            f"\n  overall: n={len(all_gaps)} p50={p50:.2f} p95={p95:.2f} "
            f"p99={p99:.2f} max={mx:.2f}"
        )
        print(
            f"  >100ms: {over_100}  >500ms: {over_500}  "
            f">1500ms: {over_1500} (FE overlay threshold)"
        )

    # Rollout (gradient update) windows.
    print("\n── gradient-update windows (rollout.end → rollout.start) ────")
    if rollout_boundaries:
        rollout_boundaries.sort(key=lambda r: r[0])
        windows: list[float] = []
        for i in range(len(rollout_boundaries) - 1):
            t0, e0 = rollout_boundaries[i]
            t1, e1 = rollout_boundaries[i + 1]
            if e0 == "rollout.end" and e1 == "rollout.start":
                windows.append(t1 - t0)
        if windows:
            sg = sorted(windows)
            p95 = sg[int(0.95 * (len(sg) - 1))]
            print(
                f"  n={len(windows)} mean={statistics.mean(windows):.2f} "
                f"p50={statistics.median(windows):.2f} p95={p95:.2f} "
                f"max={max(windows):.2f}"
            )
        else:
            print("  no end→start pairs observed")
    else:
        print("  no rollout boundaries captured")


if __name__ == "__main__":
    main()
