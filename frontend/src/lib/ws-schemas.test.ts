import { describe, it, expect } from 'vitest'
import {
  envFramePayloadSchema,
  trainingMetricsSchema,
  trainingStatusSchema,
} from './ws-schemas'

describe('trainingMetricsSchema (A6)', () => {
  it('parses a well-formed snake_case payload into camelCase TrainingMetrics', () => {
    const result = trainingMetricsSchema.safeParse({
      step: 1024,
      episode: 5,
      mean_reward: 0.75,
      win_rate: 0.6,
      policy_loss: 0.01,
      value_loss: 0.02,
    })
    expect(result.success).toBe(true)
    if (!result.success) return
    expect(result.data).toEqual({
      step: 1024,
      episode: 5,
      meanReward: 0.75,
      winRate: 0.6,
      policyLoss: 0.01,
      valueLoss: 0.02,
    })
  })

  it('rejects when a required numeric field is missing', () => {
    const result = trainingMetricsSchema.safeParse({
      step: 1024,
      episode: 5,
      // mean_reward missing
      win_rate: 0.6,
      policy_loss: 0.01,
      value_loss: 0.02,
    })
    expect(result.success).toBe(false)
  })

  it('rejects when a numeric field arrives as a string', () => {
    // Without zod, this would have made it through `snakeToCamel` and
    // poisoned `Math.max(prev.currentStep, payload.step)` with a
    // string-coerced NaN. The schema blocks the message at the door.
    const result = trainingMetricsSchema.safeParse({
      step: '1024',
      episode: 5,
      mean_reward: 0.5,
      win_rate: 0.5,
      policy_loss: 0,
      value_loss: 0,
    })
    expect(result.success).toBe(false)
  })
})

describe('trainingStatusSchema (A6)', () => {
  it('accepts a partial payload with only the state field', () => {
    const result = trainingStatusSchema.safeParse({ state: 'running' })
    expect(result.success).toBe(true)
    if (!result.success) return
    expect(result.data).toEqual({ state: 'running' })
  })

  it('camelizes every present optional field', () => {
    const result = trainingStatusSchema.safeParse({
      state: 'paused',
      current_step: 500,
      current_episode: 7,
      bot_level: 3,
      experiment_id: 'exp-abc',
      title: 'my-run',
    })
    expect(result.success).toBe(true)
    if (!result.success) return
    expect(result.data).toEqual({
      state: 'paused',
      currentStep: 500,
      currentEpisode: 7,
      botLevel: 3,
      experimentId: 'exp-abc',
      title: 'my-run',
    })
  })

  it('preserves explicit null on experiment_id + title (BE sentinel for "no run")', () => {
    const result = trainingStatusSchema.safeParse({
      state: 'stopped',
      experiment_id: null,
      title: null,
    })
    expect(result.success).toBe(true)
    if (!result.success) return
    expect(result.data.experimentId).toBeNull()
    expect(result.data.title).toBeNull()
  })

  it('rejects an unknown state value (CTA-gate safety)', () => {
    const result = trainingStatusSchema.safeParse({ state: 'initializing' })
    expect(result.success).toBe(false)
  })
})

describe('envFramePayloadSchema (A6)', () => {
  it('parses a complete env_frame payload into camelCase EnvFramePayload', () => {
    const wireFrame = { score1: 5, score2: 3 } // intentionally minimal
    const result = envFramePayloadSchema.safeParse({
      env_id: 2,
      frame: wireFrame,
      score: [5, 3],
      state_name: 'round',
      step: 4096,
    })
    expect(result.success).toBe(true)
    if (!result.success) return
    expect(result.data.envId).toBe(2)
    expect(result.data.score).toEqual([5, 3])
    expect(result.data.stateName).toBe('round')
    expect(result.data.step).toBe(4096)
    // Frame is passed through untransformed at this layer; the handler
    // applies snakeToCamel to it separately because it's a deep nested
    // object that would duplicate the engine model to validate fully.
    expect(result.data.frame).toBe(wireFrame)
  })

  it('rejects when env_id is negative', () => {
    const result = envFramePayloadSchema.safeParse({
      env_id: -1,
      frame: {},
      score: [0, 0],
      state_name: 'round',
      step: 0,
    })
    expect(result.success).toBe(false)
  })

  it('rejects when env_id is a string (BE-bug guard against the BatchTabBar map crash)', () => {
    const result = envFramePayloadSchema.safeParse({
      env_id: '2',
      frame: {},
      score: [0, 0],
      state_name: 'round',
      step: 0,
    })
    expect(result.success).toBe(false)
  })

  it('rejects when score is not a 2-tuple', () => {
    const result = envFramePayloadSchema.safeParse({
      env_id: 0,
      frame: {},
      score: [0],
      state_name: 'round',
      step: 0,
    })
    expect(result.success).toBe(false)
  })
})
