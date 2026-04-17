"""Checkpoint comparison chart generator.

Produces a multi-panel chart visualizing how model performance evolves across
training checkpoints. Each panel shows one metric (win_rate, avg_score,
avg_rally_length, avg_episode_length) plotted vs. checkpoint label.

Charts are rendered with matplotlib (Agg backend — no display required) and
saved as PNG files suitable for embedding in markdown reports.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import matplotlib

matplotlib.use("Agg")  # headless rendering — must be set before pyplot import
import matplotlib.pyplot as plt  # noqa: E402

from backend.rl.evaluator import EvalResult


@dataclass(frozen=True)
class CheckpointSeries:
    """One checkpoint's results across multiple bot levels."""

    label: str  # e.g. "10K", "20K", or model UUID prefix
    results: list[EvalResult]  # one EvalResult per bot level


def render_comparison_chart(
    series: list[CheckpointSeries],
    output_path: str | Path,
    *,
    title: str = "Checkpoint Comparison",
) -> Path:
    """Render a 2x2 grid comparing checkpoints across 4 metrics.

    Each subplot has bot_level on the x-axis and one metric on the y-axis,
    with one line per checkpoint.
    """
    if not series:
        raise ValueError("Cannot render chart with empty series list")

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    metrics = [
        ("win_rate", "Win Rate", (0.0, 1.0)),
        ("avg_score", "Avg Score", (0.0, 15.0)),
        ("avg_rally_length", "Avg Rally Length", None),
        ("avg_episode_length", "Avg Episode Length (frames)", None),
    ]

    fig, axes = plt.subplots(2, 2, figsize=(12, 8))
    fig.suptitle(title, fontsize=14, fontweight="bold")

    for ax, (attr, label, ylim) in zip(axes.flat, metrics):
        for cs in series:
            sorted_results = sorted(cs.results, key=lambda r: r.bot_level)
            xs = [r.bot_level for r in sorted_results]
            ys = [getattr(r, attr) for r in sorted_results]
            ax.plot(xs, ys, marker="o", label=cs.label, linewidth=2)
        ax.set_xlabel("Bot Level")
        ax.set_ylabel(label)
        ax.set_title(label)
        ax.set_xticks([1, 2, 3, 4, 5])
        ax.grid(True, alpha=0.3)
        if ylim is not None:
            ax.set_ylim(*ylim)
        ax.legend(loc="best", fontsize=8)

    plt.tight_layout()
    fig.savefig(output_path, dpi=100, bbox_inches="tight")
    plt.close(fig)

    return output_path


def render_progression_chart(
    series: list[CheckpointSeries],
    output_path: str | Path,
    *,
    bot_level: int,
    title: str | None = None,
) -> Path:
    """Render a progression chart for a single bot level across checkpoints.

    X-axis: checkpoint label (in order). Y-axis: metric values.
    Useful for visualizing training progress at one difficulty.
    """
    if not series:
        raise ValueError("Cannot render chart with empty series list")

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    labels: list[str] = []
    win_rates: list[float] = []
    avg_scores: list[float] = []
    rally_lengths: list[float] = []

    for cs in series:
        match = next(
            (r for r in cs.results if r.bot_level == bot_level), None
        )
        if match is None:
            continue
        labels.append(cs.label)
        win_rates.append(match.win_rate)
        avg_scores.append(match.avg_score)
        rally_lengths.append(match.avg_rally_length)

    if not labels:
        raise ValueError(f"No results for bot_level={bot_level} in any series")

    fig, ax1 = plt.subplots(figsize=(10, 6))
    fig.suptitle(title or f"Training Progression — Bot Level {bot_level}")

    x = list(range(len(labels)))
    ax1.set_xlabel("Checkpoint")
    ax1.set_ylabel("Win Rate / Avg Score (normalized)")
    ax1.set_xticks(x)
    ax1.set_xticklabels(labels, rotation=45, ha="right")

    ax1.plot(x, win_rates, marker="o", color="tab:blue", label="Win Rate", linewidth=2)
    ax1.plot(
        x,
        [s / 15.0 for s in avg_scores],
        marker="s",
        color="tab:green",
        label="Avg Score (÷15)",
        linewidth=2,
    )
    ax1.set_ylim(0.0, 1.05)
    ax1.grid(True, alpha=0.3)

    ax2 = ax1.twinx()
    ax2.set_ylabel("Avg Rally Length")
    ax2.plot(
        x, rally_lengths, marker="^", color="tab:orange", label="Rally Length", linewidth=2
    )

    lines1, labels1 = ax1.get_legend_handles_labels()
    lines2, labels2 = ax2.get_legend_handles_labels()
    ax1.legend(lines1 + lines2, labels1 + labels2, loc="upper left")

    plt.tight_layout()
    fig.savefig(output_path, dpi=100, bbox_inches="tight")
    plt.close(fig)

    return output_path
