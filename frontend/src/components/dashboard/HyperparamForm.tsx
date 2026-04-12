import type { Hyperparams } from '../../lib/types'
import './HyperparamForm.css'

// DEFAULT_HYPERPARAMS lives in its own file so this module stays
// component-only (react-refresh/only-export-components).

interface HyperparamFormProps {
  /** Current hyperparameter values (controlled). */
  params: Hyperparams
  /** Emitted when any hyperparameter field changes. */
  onParamsChange: (next: Hyperparams) => void
  /** Disable all inputs (e.g. while disconnected). */
  disabled: boolean
}

const FIELD_KEYS: Array<keyof Hyperparams> = [
  'learning_rate',
  'n_steps',
  'batch_size',
  'gamma',
  'clip_range',
]

/**
 * HyperparamForm — a controlled input form for PPO hyperparameters.
 *
 * Option A (2026-04-12): bot_level was removed from this form. The
 * dashboard has a single source of truth for difficulty — the
 * "Bot Level" L1–L5 buttons in <TrainingControls /> bound to
 * ``status.botLevel``. Clicking those fires ``training:set_level``
 * directly (accepted in any state including 'stopped'); the next
 * ``training:start`` carries no ``bot_level`` field, and the BE
 * dispatcher substitutes ``status.bot_level`` (handlers.py:131-135,
 * schemas.py:92). This eliminates the two-source inconsistency where
 * the form's dropdown silently overrode a freshly-set level.
 *
 * Intentionally does NOT render a submit button: the single Start
 * control lives in <TrainingControls /> to avoid a duplicate-CTA UX
 * regression. Submit via that button.
 */
export function HyperparamForm({
  params,
  onParamsChange,
  disabled,
}: HyperparamFormProps) {
  const handleFieldChange = (key: keyof Hyperparams, value: string) => {
    const num = Number(value)
    if (Number.isNaN(num)) return
    onParamsChange({ ...params, [key]: num })
  }

  return (
    <section
      className="hyperparam-form card"
      aria-labelledby="hyperparam-form-title"
    >
      <h3 className="hyperparam-form-title" id="hyperparam-form-title">
        Hyperparameters
      </h3>

      <div className="hyperparam-form-grid">
        {FIELD_KEYS.map(key => {
          const fieldId = `hyperparam-${key}`
          return (
            <div key={key}>
              <label className="hyperparam-form-label" htmlFor={fieldId}>
                {key}
              </label>
              <input
                id={fieldId}
                type="number"
                step="any"
                value={params[key]}
                onChange={e => handleFieldChange(key, e.target.value)}
                className="hyperparam-form-input"
                disabled={disabled}
              />
            </div>
          )
        })}
      </div>

      <p className="hyperparam-form-hint">
        Adjust values, then press <strong>Start</strong> above to begin training.
        Bot level is picked via the <strong>L1–L5</strong> buttons above.
      </p>
    </section>
  )
}
