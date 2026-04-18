import { useMemo, useState } from 'react'
import type { Hyperparams } from '../../lib/types'
import {
  HYPERPARAM_SCHEMA,
  type HyperparamFieldSchema,
  type HyperparamKey,
  validateHyperparam,
  normalizeHyperparam,
  formatScalar,
} from '../../lib/hyperparams'
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

/**
 * HyperparamForm — a controlled input form for PPO hyperparameters.
 *
 * Designer spec v2 (`docs/DESIGN-HYPERPARAM-FORM.md`, commit
 * 5c83b9dd on yoon/designer) organizes the 10 fields into two
 * collapsible groups — Basic (expanded by default) and Advanced
 * (collapsed). Slider controls land on `total_timesteps` and
 * `ent_coef` per §3. Every field gets a one-line Korean hint plus
 * the `(default: X)` meta next to the label.
 *
 * Validation is inline per §4: a red border + an error message
 * below the field when the value falls outside the schema range,
 * and `onBlur` normalization (clamp + int-round). The parent uses
 * the `aria-invalid` signal on any field to gate Start — in
 * practice that gating lives in `Dashboard.handleStart`.
 *
 * Option A (2026-04-12) still holds: `bot_level` is NOT in this
 * form. The L1–L5 buttons in `<TrainingControls />` own the
 * difficulty dial exclusively.
 *
 * Intentionally does NOT render a submit button: the single Start
 * control lives in `<TrainingControls />`.
 */
export function HyperparamForm({
  params,
  onParamsChange,
  disabled,
}: HyperparamFormProps) {
  // Advanced group collapsed by default per Designer §2. Basic is
  // always open (no collapse affordance needed).
  const [advancedOpen, setAdvancedOpen] = useState(false)

  const basicFields = useMemo(
    () => HYPERPARAM_SCHEMA.filter(f => f.group === 'basic'),
    [],
  )
  const advancedFields = useMemo(
    () => HYPERPARAM_SCHEMA.filter(f => f.group === 'advanced'),
    [],
  )

  const setField = (key: HyperparamKey, raw: string) => {
    // Accept partial input (empty string, "-", "0.") without thrashing
    // the state — users type digit by digit. We only reject values
    // that fail Number() entirely.
    const num = Number(raw)
    if (raw !== '' && Number.isNaN(num)) return
    onParamsChange({ ...params, [key]: num })
  }

  const normalizeOnBlur = (key: HyperparamKey) => {
    const current = Number(params[key])
    const normalized = normalizeHyperparam(key, current)
    if (normalized !== current) {
      onParamsChange({ ...params, [key]: normalized })
    }
  }

  const resetGroup = (group: 'basic' | 'advanced') => {
    const next = { ...params }
    for (const f of HYPERPARAM_SCHEMA) {
      if (f.group === group) {
        (next as Record<string, number>)[f.key] = f.default
      }
    }
    onParamsChange(next)
  }

  return (
    <section
      className="hyperparam-form card"
      aria-labelledby="hyperparam-form-title"
    >
      <h3 className="hyperparam-form-title" id="hyperparam-form-title">
        Hyperparameters
      </h3>

      <HyperparamGroupView
        title="Basic"
        open
        fields={basicFields}
        params={params}
        disabled={disabled}
        onFieldInput={setField}
        onFieldBlur={normalizeOnBlur}
        onReset={() => resetGroup('basic')}
      />

      <HyperparamGroupView
        title="Advanced"
        collapsible
        open={advancedOpen}
        onToggle={() => setAdvancedOpen(v => !v)}
        fields={advancedFields}
        params={params}
        disabled={disabled}
        onFieldInput={setField}
        onFieldBlur={normalizeOnBlur}
        onReset={() => resetGroup('advanced')}
      />

      <p className="hyperparam-form-hint">
        Adjust values, then press <strong>Start</strong> above to begin training.
        Bot level is picked via the <strong>L1–L5</strong> buttons above.
      </p>
    </section>
  )
}

/**
 * Collapsible group renderer. Extracted so the Basic + Advanced
 * blocks share the same chrome (header, chevron, grid, reset link)
 * while each owning its own open/closed state from the parent.
 */
interface HyperparamGroupViewProps {
  title: string
  fields: readonly HyperparamFieldSchema[]
  params: Hyperparams
  disabled: boolean
  onFieldInput: (key: HyperparamKey, raw: string) => void
  onFieldBlur: (key: HyperparamKey) => void
  onReset: () => void
  open: boolean
  collapsible?: boolean
  onToggle?: () => void
}

function HyperparamGroupView(props: HyperparamGroupViewProps) {
  const {
    title,
    fields,
    params,
    disabled,
    onFieldInput,
    onFieldBlur,
    onReset,
    open,
    collapsible,
    onToggle,
  } = props

  const groupId = `hyperparam-group-${title.toLowerCase()}`
  const contentId = `${groupId}-content`

  return (
    <div className="hyperparam-form-group" role="group" aria-labelledby={groupId}>
      <div className="hyperparam-form-group-header">
        {collapsible ? (
          <button
            type="button"
            className="hyperparam-form-group-title hyperparam-form-group-title--button"
            id={groupId}
            aria-expanded={open}
            aria-controls={contentId}
            onClick={onToggle}
          >
            <span
              className={`hyperparam-form-group-chevron${open ? ' hyperparam-form-group-chevron--open' : ''}`}
              aria-hidden="true"
            >
              ▸
            </span>
            {title}
          </button>
        ) : (
          <h4 className="hyperparam-form-group-title" id={groupId}>
            {title}
          </h4>
        )}
        {open && (
          <button
            type="button"
            className="hyperparam-form-group-reset"
            onClick={onReset}
            disabled={disabled}
          >
            Reset to defaults
          </button>
        )}
      </div>

      {open && (
        <div className="hyperparam-form-grid" id={contentId}>
          {fields.map(f => (
            <HyperparamField
              key={f.key}
              schema={f}
              value={Number(params[f.key])}
              disabled={disabled}
              onInput={raw => onFieldInput(f.key, raw)}
              onBlur={() => onFieldBlur(f.key)}
            />
          ))}
        </div>
      )}
    </div>
  )
}

interface HyperparamFieldProps {
  schema: HyperparamFieldSchema
  value: number
  disabled: boolean
  onInput: (raw: string) => void
  onBlur: () => void
}

/**
 * Single field (label + meta + hint + control + error). Slider
 * fields render `<input type="range">` plus a width-stable numeric
 * readout chip per Designer §3; number fields get a `<input
 * type="number">` only. Error state is driven by
 * `validateHyperparam` on every render.
 */
function HyperparamField({
  schema,
  value,
  disabled,
  onInput,
  onBlur,
}: HyperparamFieldProps) {
  const fieldId = `hyperparam-${schema.key}`
  const validation = validateHyperparam(schema.key, value)
  const errorId = `${fieldId}-error`

  const commonProps = {
    id: fieldId,
    value: Number.isNaN(value) ? '' : String(value),
    onChange: (e: React.ChangeEvent<HTMLInputElement>) => onInput(e.target.value),
    onBlur,
    disabled,
    'aria-invalid': !validation.valid,
    'aria-describedby': validation.valid ? undefined : errorId,
    className: `hyperparam-form-input${validation.valid ? '' : ' hyperparam-form-input--invalid'}`,
  }

  return (
    <div className="hyperparam-form-field">
      <label className="hyperparam-form-label" htmlFor={fieldId}>
        <span className="hyperparam-form-label-name">{schema.label}</span>
        <span className="hyperparam-form-label-default">
          (default: {formatScalar(schema.default, schema)})
        </span>
      </label>
      <p className="hyperparam-form-field-hint" title={schema.hint}>
        {schema.hint}
      </p>
      {schema.slider ? (
        <div className="hyperparam-form-slider-row">
          <input
            {...commonProps}
            type="range"
            min={schema.range[0]}
            max={schema.range[1]}
            step={schema.step}
            aria-valuetext={formatScalar(value, schema)}
            className={`hyperparam-form-slider${validation.valid ? '' : ' hyperparam-form-slider--invalid'}`}
          />
          <span
            className="hyperparam-form-slider-readout"
            aria-hidden="true"
          >
            {formatScalar(value, schema)}
          </span>
        </div>
      ) : (
        <input
          {...commonProps}
          type="number"
          min={schema.range[0]}
          max={schema.range[1]}
          step={schema.step}
        />
      )}
      {!validation.valid && (
        <span
          id={errorId}
          className="hyperparam-form-field-error"
          role="alert"
        >
          {validation.message}
        </span>
      )}
    </div>
  )
}
