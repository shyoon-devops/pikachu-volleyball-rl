import { describe, it, expect } from 'vitest'
import {
  HYPERPARAM_SCHEMA,
  HYPERPARAM_SCHEMA_BY_KEY,
  DEFAULT_HYPERPARAMS_EXTENDED,
  HYPERPARAM_WIRE_POSITION,
  validateHyperparam,
  normalizeHyperparam,
  formatScalar,
} from './hyperparams'

describe('HYPERPARAM_SCHEMA', () => {
  it('covers every key listed in DEFAULT_HYPERPARAMS_EXTENDED', () => {
    const keys = HYPERPARAM_SCHEMA.map(f => f.key)
    expect(keys.sort()).toEqual(
      Object.keys(DEFAULT_HYPERPARAMS_EXTENDED).sort(),
    )
  })

  it('groups split into exactly 5 basic + 5 advanced entries (Designer §2)', () => {
    const basic = HYPERPARAM_SCHEMA.filter(f => f.group === 'basic')
    const advanced = HYPERPARAM_SCHEMA.filter(f => f.group === 'advanced')
    expect(basic).toHaveLength(5)
    expect(advanced).toHaveLength(5)
  })

  it('default values fall inside each field\'s declared range', () => {
    for (const f of HYPERPARAM_SCHEMA) {
      const [min, max] = f.range
      expect(f.default).toBeGreaterThanOrEqual(min)
      expect(f.default).toBeLessThanOrEqual(max)
    }
  })

  it('integer fields have integer defaults', () => {
    for (const f of HYPERPARAM_SCHEMA) {
      if (f.integer) expect(Number.isInteger(f.default)).toBe(true)
    }
  })

  it('keys marked as slider (total_timesteps, ent_coef) have the flag', () => {
    // Designer spec §3 names exactly these two.
    expect(HYPERPARAM_SCHEMA_BY_KEY.total_timesteps.slider).toBe(true)
    expect(HYPERPARAM_SCHEMA_BY_KEY.ent_coef.slider).toBe(true)
    // Others should NOT be sliders.
    expect(HYPERPARAM_SCHEMA_BY_KEY.learning_rate.slider).not.toBe(true)
    expect(HYPERPARAM_SCHEMA_BY_KEY.n_envs.slider).not.toBe(true)
  })
})

describe('validateHyperparam', () => {
  it('accepts a default value as valid', () => {
    for (const f of HYPERPARAM_SCHEMA) {
      expect(validateHyperparam(f.key, f.default).valid).toBe(true)
    }
  })

  it('rejects values below the minimum with a range hint', () => {
    const result = validateHyperparam('n_envs', 0)
    expect(result.valid).toBe(false)
    expect(result.message).toMatch(/Range/)
  })

  it('rejects values above the maximum', () => {
    expect(validateHyperparam('ent_coef', 0.06).valid).toBe(false)
    expect(validateHyperparam('gae_lambda', 1.5).valid).toBe(false)
  })

  it('rejects NaN input', () => {
    expect(validateHyperparam('learning_rate', Number.NaN).valid).toBe(false)
  })

  it('flags auto-round when a non-integer lands in an integer field', () => {
    const r = validateHyperparam('n_epochs', 12.3)
    expect(r.valid).toBe(true)
    expect(r.autoRounded).toBe(true)
  })
})

describe('normalizeHyperparam', () => {
  it('clamps out-of-range values into the field\'s bounds', () => {
    expect(normalizeHyperparam('n_envs', 0)).toBe(1)
    expect(normalizeHyperparam('n_envs', 100)).toBe(32)
    expect(normalizeHyperparam('gae_lambda', 1.5)).toBe(1.0)
  })

  it('rounds non-integer values in integer fields', () => {
    expect(normalizeHyperparam('n_epochs', 12.6)).toBe(13)
    expect(normalizeHyperparam('n_epochs', 12.3)).toBe(12)
  })

  it('leaves valid floats untouched', () => {
    expect(normalizeHyperparam('gamma', 0.95)).toBe(0.95)
  })
})

describe('HYPERPARAM_WIRE_POSITION (Designer spec FC-R5)', () => {
  // BE cc4daaf3 lifted these 5 fields to the top level of
  // WsTrainingStartPayload; the rest ride inside `hyperparams`.
  it('pins the 5 top-level fields to match BE contract', () => {
    expect(HYPERPARAM_WIRE_POSITION.total_timesteps).toBe('top-level')
    expect(HYPERPARAM_WIRE_POSITION.n_envs).toBe('top-level')
    expect(HYPERPARAM_WIRE_POSITION.n_epochs).toBe('top-level')
    expect(HYPERPARAM_WIRE_POSITION.ent_coef).toBe('top-level')
    expect(HYPERPARAM_WIRE_POSITION.gae_lambda).toBe('top-level')
  })

  it('keeps the PPO constructor args (learning_rate et al) in the blob', () => {
    expect(HYPERPARAM_WIRE_POSITION.learning_rate).toBe('hyperparams-blob')
    expect(HYPERPARAM_WIRE_POSITION.n_steps).toBe('hyperparams-blob')
    expect(HYPERPARAM_WIRE_POSITION.batch_size).toBe('hyperparams-blob')
    expect(HYPERPARAM_WIRE_POSITION.gamma).toBe('hyperparams-blob')
    expect(HYPERPARAM_WIRE_POSITION.clip_range).toBe('hyperparams-blob')
  })
})

describe('formatScalar', () => {
  it('abbreviates large integers to K / M', () => {
    const tsSchema = HYPERPARAM_SCHEMA_BY_KEY.total_timesteps
    expect(formatScalar(2_000_000, tsSchema)).toBe('2M')
    expect(formatScalar(2_500_000, tsSchema)).toBe('2.5M')
    expect(formatScalar(100_000, tsSchema)).toBe('100K')
  })

  it('uses locale separators for small integers', () => {
    const nEnvs = HYPERPARAM_SCHEMA_BY_KEY.n_envs
    expect(formatScalar(8, nEnvs)).toBe('8')
  })

  it('formats floats at step-derived precision', () => {
    const entCoef = HYPERPARAM_SCHEMA_BY_KEY.ent_coef
    expect(formatScalar(0.012, entCoef)).toBe('0.012')
    const gamma = HYPERPARAM_SCHEMA_BY_KEY.gamma
    expect(formatScalar(0.99, gamma)).toBe('0.990')
  })
})
