import type { Hyperparams } from '../../lib/types'
import './HyperparamsSummary.css'

/**
 * Compact hyperparameters card for the training-run detail page
 * (FC-R8b, 2026-04-18). Shows the 10 canonical PPO knobs in the
 * same order as HyperparamForm so the Start form and the run
 * summary read identically.
 *
 * Data source: `TrainingRun.hyperparams` on `/api/training/runs`
 * — BE-WAITING (BE-T10 ticket). Until BE persists the submitted
 * hyperparams on `training_runs.register`, we render a "no data"
 * placeholder so the UI doesn't lie about knobs we can't verify.
 *
 * Field order mirrors `HYPERPARAM_SCHEMA` in lib/hyperparams.ts.
 * Values render with appropriate formatting (scientific for the
 * learning_rate + entropy coefficient, integer for counts, float
 * with fixed decimals for ratios).
 */

export interface HyperparamsSummaryProps {
  /** Partial: BE may emit an earlier snapshot with fewer fields. */
  hyperparams?: Partial<Hyperparams> | null
}

interface Field {
  key: keyof Hyperparams
  label: string
  format: (v: number) => string
}

const FIELDS: Field[] = [
  { key: 'total_timesteps', label: 'total_timesteps', format: n => n.toLocaleString() },
  { key: 'n_envs',          label: 'n_envs',          format: n => n.toString() },
  { key: 'learning_rate',   label: 'learning_rate',   format: n => n.toExponential(1) },
  { key: 'n_steps',         label: 'n_steps',         format: n => n.toLocaleString() },
  { key: 'batch_size',      label: 'batch_size',      format: n => n.toLocaleString() },
  { key: 'n_epochs',        label: 'n_epochs',        format: n => n.toString() },
  { key: 'gamma',           label: 'gamma',           format: n => n.toFixed(4) },
  { key: 'clip_range',      label: 'clip_range',      format: n => n.toFixed(2) },
  { key: 'ent_coef',        label: 'ent_coef',        format: n => n.toExponential(1) },
  { key: 'gae_lambda',      label: 'gae_lambda',      format: n => n.toFixed(3) },
]

function isPresent(v: number | undefined): v is number {
  return typeof v === 'number' && Number.isFinite(v)
}

export function HyperparamsSummary({ hyperparams }: HyperparamsSummaryProps) {
  const hasAny = hyperparams && Object.values(hyperparams).some(isPresent)

  if (!hasAny) {
    return (
      <section className="hyperparams-summary hyperparams-summary--empty card" aria-label="Hyperparameters">
        <h3 className="hyperparams-summary-title">Hyperparameters</h3>
        <p className="hyperparams-summary-empty text-muted">
          학습 파라미터 정보 준비 중입니다. BE에서 저장된 하이퍼파라미터를 노출하면 이 자리에 표시됩니다.
        </p>
      </section>
    )
  }

  return (
    <section className="hyperparams-summary card" aria-label="Hyperparameters">
      <h3 className="hyperparams-summary-title">Hyperparameters</h3>
      <dl className="hyperparams-summary-grid">
        {FIELDS.map(f => {
          const raw = hyperparams?.[f.key]
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
