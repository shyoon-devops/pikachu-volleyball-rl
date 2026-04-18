import type { Hyperparams } from '../../lib/types'
import './HyperparamsSummary.css'

/**
 * Compact hyperparameters card for the training-run detail page
 * (FC-R8b, 2026-04-18). Shows the 10 canonical PPO knobs in the
 * same order as HyperparamForm so the Start form and the run
 * summary read identically.
 *
 * Data source: `TrainingRun.hyperparams` on `/api/training/runs`.
 * BE populates all 10 knobs on the training_runs aggregate.
 *
 * Lookup uses BOTH snake_case AND camelCase keys (FC-R9a): the
 * shared `snakeToCamel` transform on every api.ts response rewrites
 * `total_timesteps` → `totalTimesteps` before it lands here, but
 * the underlying Hyperparams TS type preserves snake_case. Without
 * the dual lookup every multi-word key rendered `—` and only
 * `gamma` (no underscore, unchanged by the transform) displayed.
 *
 * Formatting rules per field:
 *   - learning_rate / ent_coef → scientific
 *   - total_timesteps / n_steps / batch_size → locale-formatted int
 *   - gamma → 4 dp, gae_lambda → 3 dp, clip_range → 2 dp
 *   - n_envs / n_epochs → plain int
 */

export interface HyperparamsSummaryProps {
  /** Partial: BE may emit an earlier snapshot with fewer fields. */
  hyperparams?: Partial<Hyperparams> | null
}

interface Field {
  /** Snake-case key from the FE's `Hyperparams` type. */
  key: keyof Hyperparams
  /** Camel-case alias — what the shared `snakeToCamel` transform
   *  in api.ts produces on the wire payload. Omit for keys that are
   *  identical in both cases (e.g. `gamma`). */
  camelKey?: string
  label: string
  format: (v: number) => string
}

const FIELDS: Field[] = [
  { key: 'total_timesteps', camelKey: 'totalTimesteps', label: 'total_timesteps', format: n => n.toLocaleString() },
  { key: 'n_envs',          camelKey: 'nEnvs',          label: 'n_envs',          format: n => n.toString() },
  { key: 'learning_rate',   camelKey: 'learningRate',   label: 'learning_rate',   format: n => n.toExponential(1) },
  { key: 'n_steps',         camelKey: 'nSteps',         label: 'n_steps',         format: n => n.toLocaleString() },
  { key: 'batch_size',      camelKey: 'batchSize',      label: 'batch_size',      format: n => n.toLocaleString() },
  { key: 'n_epochs',        camelKey: 'nEpochs',        label: 'n_epochs',        format: n => n.toString() },
  { key: 'gamma',                                       label: 'gamma',           format: n => n.toFixed(4) },
  { key: 'clip_range',      camelKey: 'clipRange',      label: 'clip_range',      format: n => n.toFixed(2) },
  { key: 'ent_coef',        camelKey: 'entCoef',        label: 'ent_coef',        format: n => n.toExponential(1) },
  { key: 'gae_lambda',      camelKey: 'gaeLambda',      label: 'gae_lambda',      format: n => n.toFixed(3) },
]

function isPresent(v: unknown): v is number {
  // Null-only fallback (FC-R9a): 0 is a perfectly valid
  // hyperparameter value (e.g. ent_coef=0 for zero-entropy), so
  // `value && ...` truthy checks would mis-render. Number.isFinite
  // excludes NaN / Infinity while accepting the full finite range.
  return typeof v === 'number' && Number.isFinite(v)
}

function readField(
  hp: Partial<Hyperparams> | Record<string, unknown> | null | undefined,
  f: Field,
): number | undefined {
  if (!hp) return undefined
  // Prefer snake_case (internal type), fall back to camel (wire).
  const bag = hp as Record<string, unknown>
  const snake = bag[f.key]
  if (isPresent(snake)) return snake
  if (f.camelKey) {
    const camel = bag[f.camelKey]
    if (isPresent(camel)) return camel
  }
  return undefined
}

export function HyperparamsSummary({ hyperparams }: HyperparamsSummaryProps) {
  const hasAny = FIELDS.some(f => isPresent(readField(hyperparams, f)))

  if (!hasAny) {
    return (
      <section className="hyperparams-summary hyperparams-summary--empty card" aria-label="Hyperparameters">
        <h3 className="hyperparams-summary-title">Hyperparameters</h3>
        <p className="hyperparams-summary-empty text-muted">
          Hyperparameter data not available for this run.
        </p>
      </section>
    )
  }

  return (
    <section className="hyperparams-summary card" aria-label="Hyperparameters">
      <h3 className="hyperparams-summary-title">Hyperparameters</h3>
      <dl className="hyperparams-summary-grid">
        {FIELDS.map(f => {
          const raw = readField(hyperparams, f)
          return (
            <div key={f.key} className="hyperparams-summary-item">
              <dt className="hyperparams-summary-label">{f.label}</dt>
              <dd className="hyperparams-summary-value">
                {isPresent(raw) ? f.format(raw) : '—'}
              </dd>
            </div>
          )
        })}
      </dl>
    </section>
  )
}
