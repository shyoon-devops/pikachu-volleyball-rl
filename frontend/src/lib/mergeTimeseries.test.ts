import { describe, it, expect } from 'vitest'
import { mergeTimeseries } from './mergeTimeseries'
import type { TimeseriesPoint } from './types'

const point = (step: number, value: number): TimeseriesPoint => ({
  step,
  value,
  timestamp: null,
})

describe('mergeTimeseries', () => {
  it('joins aligned steps into one TrainingMetrics per step', () => {
    // Happy path: BE writes all 4 fields per snapshot, so steps align.
    const merged = mergeTimeseries(
      [point(100, 1.5), point(200, 2.0)],
      [point(100, 0.3), point(200, 0.6)],
      [point(100, 0.8), point(200, 0.5)],
      [point(100, 0.4), point(200, 0.2)],
    )
    expect(merged).toEqual([
      { step: 100, episode: 0, meanReward: 1.5, winRate: 0.3, policyLoss: 0.8, valueLoss: 0.4 },
      { step: 200, episode: 0, meanReward: 2.0, winRate: 0.6, policyLoss: 0.5, valueLoss: 0.2 },
    ])
  })

  it('sorts by step ascending even if inputs arrive out of order', () => {
    // BE returns newest-last but defensive: if anyone sorts differently
    // the chart should still render left-to-right.
    const merged = mergeTimeseries(
      [point(300, 3), point(100, 1), point(200, 2)],
      [],
      [],
      [],
    )
    expect(merged.map(m => m.step)).toEqual([100, 200, 300])
  })

  it('defaults missing fields to 0 when a step is partial', () => {
    // Regression guard: one metric's query is empty (e.g. a field added
    // later, or filtered by $exists). Rather than drop the row, we
    // render 0 to stay consistent with the aggregate endpoint and to
    // keep the x-axis continuous.
    const merged = mergeTimeseries(
      [point(100, 1.5)],
      [], // win_rate missing entirely
      [point(100, 0.8)],
      [point(100, 0.4)],
    )
    expect(merged).toEqual([
      { step: 100, episode: 0, meanReward: 1.5, winRate: 0, policyLoss: 0.8, valueLoss: 0.4 },
    ])
  })

  it('creates a row even if only one of the four series has the step', () => {
    // Edge case: different metrics can have different step sets if BE
    // filters rows lacking a given field. A value-loss-only step still
    // deserves a row so the chart cursor stays truthful about what data
    // exists.
    const merged = mergeTimeseries([], [], [], [point(500, 0.1)])
    expect(merged).toEqual([
      { step: 500, episode: 0, meanReward: 0, winRate: 0, policyLoss: 0, valueLoss: 0.1 },
    ])
  })

  it('returns an empty array when every input is empty', () => {
    expect(mergeTimeseries([], [], [], [])).toEqual([])
  })

  it('does not mutate the inputs', () => {
    // Guard against future refactors that might `.sort()` the inputs
    // in place. The hook reuses these arrays for WS merge logic.
    const reward = [point(200, 2), point(100, 1)]
    const snapshot = [...reward]
    mergeTimeseries(reward, [], [], [])
    expect(reward).toEqual(snapshot)
  })
})
