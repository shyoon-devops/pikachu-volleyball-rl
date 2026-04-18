/**
 * Hyperparam schema — single source of truth for the FE form's
 * defaults, ranges, steps, validation, and hints. Ties the form to
 * BE (`backend/app/models/schemas.py::WsTrainingStartPayload`) so
 * the two stay in sync; if BE tightens a bound, bump `range` here.
 *
 * Kept in its own module so `HyperparamForm.tsx` can stay
 * component-only (react-refresh/only-export-components) and tests
 * can import the schema without pulling React.
 */

/**
 * Union of all hyperparam field keys. Ordering mirrors the Designer
 * spec §2 (Basic group first, then Advanced).
 */
export type HyperparamKey =
  // Basic
  | 'total_timesteps'
  | 'n_envs'
  | 'learning_rate'
  | 'n_steps'
  | 'batch_size'
  // Advanced
  | 'n_epochs'
  | 'gamma'
  | 'clip_range'
  | 'ent_coef'
  | 'gae_lambda'

export type HyperparamGroup = 'basic' | 'advanced'

export interface HyperparamFieldSchema {
  /** Wire key, matches BE (snake_case). */
  key: HyperparamKey
  /** Human-readable label (English); mono 12px in the form. */
  label: string
  group: HyperparamGroup
  /** BE-authoritative default; used by the per-group "Reset" link. */
  default: number
  /** Closed range [min, max]. Out-of-range = invalid submit. */
  range: readonly [number, number]
  /** Step size for both the number input and (if applicable) the slider. */
  step: number
  /** True when the field is a slider (track + readout chip) rather
   *  than a plain number input. Designer spec §3. */
  slider?: boolean
  /** True when the value must be a positive integer. Non-integer
   *  entries auto-round on blur (spec §4). */
  integer?: boolean
  /** One-line hint (Korean per Designer spec §1 table). */
  hint: string
}

/**
 * Static registry of every hyperparam field the form exposes. The
 * order here is the render order within each group.
 *
 * BE (`WsTrainingStartPayload`, commit cc4daaf3) accepts each of the
 * 5 new fields at the *top level* of the `training:start` payload —
 * NOT nested inside the `hyperparams` blob. `classifyField` below
 * encodes that contract so the form's submit can unbundle cleanly.
 */
export const HYPERPARAM_SCHEMA: readonly HyperparamFieldSchema[] = [
  {
    key: 'total_timesteps',
    label: 'total_timesteps',
    group: 'basic',
    default: 2_000_000,
    range: [100_000, 10_000_000],
    step: 100_000,
    slider: true,
    integer: true,
    hint: 'Training length (timestep count). Higher = longer + better-trained.',
  },
  {
    key: 'n_envs',
    label: 'n_envs',
    group: 'basic',
    default: 8,
    range: [1, 32],
    step: 1,
    integer: true,
    hint: 'Parallel env count (higher = faster but heavier on CPU).',
  },
  {
    key: 'learning_rate',
    label: 'learning_rate',
    group: 'basic',
    default: 3e-4,
    range: [1e-5, 1e-2],
    step: 1e-5,
    hint: 'Learning rate (policy/value update magnitude).',
  },
  {
    key: 'n_steps',
    label: 'n_steps',
    group: 'basic',
    default: 2048,
    range: [64, 8192],
    step: 64,
    integer: true,
    hint: 'Steps per rollout (samples per policy update).',
  },
  {
    key: 'batch_size',
    label: 'batch_size',
    group: 'basic',
    default: 64,
    range: [16, 512],
    step: 16,
    integer: true,
    hint: 'Mini-batch size per gradient step.',
  },
  {
    key: 'n_epochs',
    label: 'n_epochs',
    group: 'advanced',
    default: 10,
    range: [1, 30],
    step: 1,
    integer: true,
    hint: 'Training passes per rollout (too high → overfitting).',
  },
  {
    key: 'gamma',
    label: 'gamma',
    group: 'advanced',
    default: 0.99,
    range: [0.8, 0.9999],
    step: 0.001,
    hint: 'Discount factor (future-reward weighting).',
  },
  {
    key: 'clip_range',
    label: 'clip_range',
    group: 'advanced',
    default: 0.2,
    range: [0.05, 0.5],
    step: 0.01,
    hint: 'PPO clip range (policy-update conservativeness).',
  },
  {
    key: 'ent_coef',
    label: 'ent_coef',
    group: 'advanced',
    default: 0.01,
    range: [0.0, 0.05],
    step: 0.001,
    slider: true,
    hint: 'Exploration strength (entropy bonus). Higher = more varied actions.',
  },
  {
    key: 'gae_lambda',
    label: 'gae_lambda',
    group: 'advanced',
    default: 0.95,
    range: [0.9, 1.0],
    step: 0.01,
    hint: 'GAE smoothing (variance–bias tradeoff).',
  },
] as const

/** O(1) key lookup for the schema registry. */
export const HYPERPARAM_SCHEMA_BY_KEY: Readonly<Record<HyperparamKey, HyperparamFieldSchema>> = Object.freeze(
  HYPERPARAM_SCHEMA.reduce((acc, f) => {
    acc[f.key] = f
    return acc
  }, {} as Record<HyperparamKey, HyperparamFieldSchema>),
)

/** Fully-populated default set (used by the full-form reset link). */
export const DEFAULT_HYPERPARAMS_EXTENDED: Record<HyperparamKey, number> = Object.freeze(
  HYPERPARAM_SCHEMA.reduce((acc, f) => {
    acc[f.key] = f.default
    return acc
  }, {} as Record<HyperparamKey, number>),
)

/**
 * WS `training:start` accepts some fields top-level (BE
 * `WsTrainingStartPayload` commit cc4daaf3) and others nested inside
 * the free-form `hyperparams` dict. Classification table here keeps
 * the split in one place — if BE lifts `gamma` to top-level later,
 * flip a single entry and the submit path auto-follows.
 */
export type HyperparamWirePosition = 'top-level' | 'hyperparams-blob'

export const HYPERPARAM_WIRE_POSITION: Readonly<Record<HyperparamKey, HyperparamWirePosition>> = Object.freeze({
  total_timesteps: 'top-level',
  n_envs: 'top-level',
  n_epochs: 'top-level',
  ent_coef: 'top-level',
  gae_lambda: 'top-level',
  learning_rate: 'hyperparams-blob',
  n_steps: 'hyperparams-blob',
  batch_size: 'hyperparams-blob',
  gamma: 'hyperparams-blob',
  clip_range: 'hyperparams-blob',
})

/**
 * Validate a single field value. `valid` is the simple bool the UI
 * uses to gate submit + render the error border; `clampedHint` is
 * surfaced inline per Designer spec §4. `autoRounded` signals that
 * a non-integer was coerced to an integer on blur; callers should
 * show the "auto-rounded" toast.
 */
export interface ValidationResult {
  valid: boolean
  autoRounded: boolean
  message: string | null
}

export function validateHyperparam(
  key: HyperparamKey,
  raw: number,
): ValidationResult {
  const schema = HYPERPARAM_SCHEMA_BY_KEY[key]
  if (!schema) {
    return { valid: false, autoRounded: false, message: 'Unknown field' }
  }
  if (Number.isNaN(raw)) {
    return { valid: false, autoRounded: false, message: 'Enter a number' }
  }
  const [min, max] = schema.range
  if (raw < min || raw > max) {
    return {
      valid: false,
      autoRounded: false,
      message: `Range: ${formatScalar(min, schema)}–${formatScalar(max, schema)}`,
    }
  }
  const autoRounded = schema.integer === true && !Number.isInteger(raw)
  return { valid: true, autoRounded, message: null }
}

/**
 * Normalize user input on blur:
 *   - Out-of-range → clamp into [min, max]
 *   - Non-integer on an int field → round
 *
 * Used in addition to `validateHyperparam`; the form shows the
 * validation message during typing and applies `normalize` on blur.
 */
export function normalizeHyperparam(
  key: HyperparamKey,
  raw: number,
): number {
  const schema = HYPERPARAM_SCHEMA_BY_KEY[key]
  if (!schema || Number.isNaN(raw)) return raw
  const [min, max] = schema.range
  let n = Math.max(min, Math.min(max, raw))
  if (schema.integer) n = Math.round(n)
  return n
}

/**
 * Compact display of a scalar value for the "default:" meta + the
 * slider readout chip. Large integers get "M" / "K" abbreviations;
 * small floats retain their significant precision via toFixed.
 */
export function formatScalar(
  value: number,
  schema: HyperparamFieldSchema,
): string {
  if (!Number.isFinite(value)) return '—'
  if (schema.integer) {
    if (Math.abs(value) >= 1_000_000) {
      const m = value / 1_000_000
      return `${m % 1 === 0 ? m.toFixed(0) : m.toFixed(1)}M`
    }
    if (Math.abs(value) >= 10_000) {
      return `${(value / 1000).toFixed(0)}K`
    }
    return value.toLocaleString()
  }
  // Floats: infer precision from step. step=0.001 → 3 decimals.
  const stepStr = String(schema.step)
  const fractional = stepStr.includes('.')
    ? stepStr.split('.')[1].length
    : stepStr.includes('e-')
      ? Number(stepStr.split('e-')[1]) + 1
      : 2
  return value.toFixed(fractional)
}
