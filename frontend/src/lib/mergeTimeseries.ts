/**
 * Merge the 4 per-metric timeseries responses into the flat
 * `TrainingMetrics[]` shape the chart consumes.
 *
 * Why this exists: `/api/training/timeseries` returns one metric at a
 * time (reward, win_rate, policy_loss, value_loss), but the chart
 * plots them against a single `step` axis with each row carrying all
 * four values. BE's `MetricsCallback` writes all four fields in one
 * snapshot so steps line up 1:1 in the common case — this helper joins
 * them and tolerates partial rows when a field is missing for some
 * steps (e.g. an older snapshot written before a field existed, or
 * skipped rows filtered out by the `$exists: True` guard in
 * `MetricsService.recent_points`).
 *
 * Missing-field policy: absent fields collapse to 0 rather than being
 * dropped, matching the existing convention in `getMetricsHistory`
 * (`Number(b.avg_mean_reward ?? 0)`). 0 can draw a misleading line on
 * win_rate charts but is consistent with the rest of the pipeline; if
 * the chart ever gets a "skip missing" option we can revisit.
 *
 * Return value is sorted by step ascending so the chart can render
 * without resorting. Caller is responsible for slicing to a max-points
 * window.
 */
import type { TimeseriesPoint, TrainingMetrics } from './types'

export function mergeTimeseries(
  reward: readonly TimeseriesPoint[],
  winRate: readonly TimeseriesPoint[],
  policyLoss: readonly TimeseriesPoint[],
  valueLoss: readonly TimeseriesPoint[],
): TrainingMetrics[] {
  const byStep = new Map<number, TrainingMetrics>()

  const upsert = (step: number, patch: Partial<TrainingMetrics>): void => {
    const current = byStep.get(step) ?? {
      step,
      episode: 0,
      meanReward: 0,
      winRate: 0,
      policyLoss: 0,
      valueLoss: 0,
    }
    byStep.set(step, { ...current, ...patch })
  }

  for (const p of reward) upsert(p.step, { meanReward: p.value })
  for (const p of winRate) upsert(p.step, { winRate: p.value })
  for (const p of policyLoss) upsert(p.step, { policyLoss: p.value })
  for (const p of valueLoss) upsert(p.step, { valueLoss: p.value })

  return [...byStep.values()].sort((a, b) => a.step - b.step)
}
