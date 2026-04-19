import { useMemo, useState } from 'react'
import type { Hyperparams, LeagueSampling, TrainingMode } from '../../lib/types'
import {
  HYPERPARAM_SCHEMA,
  type HyperparamFieldSchema,
  type HyperparamKey,
  validateHyperparam,
  normalizeHyperparam,
  formatScalar,
} from '../../lib/hyperparams'
import { TitleInput, type TitleValidationState } from './TitleInput'
import './HyperparamForm.css'

/** League pool hard cap (ADR-0014 §1). Shown as the denominator in
 *  the Opponent section's pool-size chip. */
const LEAGUE_POOL_CAP = 32

// DEFAULT_HYPERPARAMS lives in its own file so this module stays
// component-only (react-refresh/only-export-components).

interface HyperparamFormProps {
  /** Current hyperparameter values (controlled). */
  params: Hyperparams
  /** Emitted when any hyperparameter field changes. */
  onParamsChange: (next: Hyperparams) => void
  /** Disable all inputs (e.g. while disconnected). */
  disabled: boolean
  /** Controlled title value (FC-R6G — lives at Dashboard so Start
   *  can pass it on the WS payload). Empty is valid; BE
   *  auto-generates on submit. */
  title: string
  onTitleChange: (next: string) => void
  /** Reports title-field validation so the Dashboard's Start gate
   *  can block on duplicates / over-length. `checking` is NOT a
   *  block — the user can still submit during an in-flight dup
   *  check; BE enforces final uniqueness on save. */
  onTitleValidationChange: (state: TitleValidationState) => void

  // ── v2.x Sprint 1 (self-play league) ───────────────────────────
  /** Opponent source: rule-based ladder vs self-play league
   *  (ADR-0014 §1). Default: bot_ladder. */
  opponentMode: TrainingMode
  onOpponentModeChange: (next: TrainingMode) => void
  /** Self-play sampling strategy (ADR-0014 §2). Only consumed by BE
   *  when opponent_mode is self_play; shown only in that branch. */
  samplingStrategy: LeagueSampling
  onSamplingStrategyChange: (next: LeagueSampling) => void
  /** Live pool fill (denominator capped at 32). `null` means the
   *  standings fetch hasn't landed yet — chip renders `— / 32`. */
  leaguePoolSize: number | null
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
  title,
  onTitleChange,
  onTitleValidationChange,
  opponentMode,
  onOpponentModeChange,
  samplingStrategy,
  onSamplingStrategyChange,
  leaguePoolSize,
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

      <TitleInput
        value={title}
        onChange={onTitleChange}
        disabled={disabled}
        onValidationChange={onTitleValidationChange}
      />

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

      {/*
        Opponent section — v2.x Sprint 1 (docs/design/SELF-PLAY-UX.md §1).
        Placed between Basic and Advanced, expanded by default. The
        `Rule-based` branch leaves the existing L1–L5 bot_level logic
        (owned by TrainingControls) as the source; the `Self-play
        league` branch unlocks the sampling radio + pool-size chip.
        Empty-pool fallback is handled BE-side — this form never
        blocks submit on pool state.
      */}
      <OpponentSection
        disabled={disabled}
        mode={opponentMode}
        onModeChange={onOpponentModeChange}
        sampling={samplingStrategy}
        onSamplingChange={onSamplingStrategyChange}
        poolSize={leaguePoolSize}
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

/**
 * Opponent section (v2.x Sprint 1 — docs/design/SELF-PLAY-UX.md §1).
 *
 * Segmented control flips between rule-ladder and self-play training.
 * The self-play branch reveals a sampling strategy radio + read-only
 * pool-size chip. The form-state lives at the Dashboard so
 * `handleStart` can include `mode` / `sampling` on the `training:start`
 * payload (BE-impl-7 extended WsTrainingStartPayload for these keys).
 *
 * Empty-pool handling is BE-side: if a self-play run is launched
 * against a pool size of 0, `_build_league_opponent_provider`
 * transparently falls back to bot_ladder. We surface that possibility
 * in the hint text; submit is never blocked on pool state.
 */
interface OpponentSectionProps {
  disabled: boolean
  mode: TrainingMode
  onModeChange: (next: TrainingMode) => void
  sampling: LeagueSampling
  onSamplingChange: (next: LeagueSampling) => void
  poolSize: number | null
}

const SAMPLING_OPTIONS: Array<{ value: LeagueSampling; label: string; hint: string }> = [
  { value: 'pfsp',           label: 'PFSP (default)',    hint: 'Weights weak opponents higher via (1 − winrate)²' },
  { value: 'elo_proximity',  label: 'Elo proximity',     hint: 'Prefers opponents near the current Elo' },
  { value: 'uniform',        label: 'Uniform',           hint: 'Draws opponents with equal probability' },
]

function OpponentSection({
  disabled,
  mode,
  onModeChange,
  sampling,
  onSamplingChange,
  poolSize,
}: OpponentSectionProps) {
  const isSelfPlay = mode === 'self_play'
  return (
    <div
      className="hyperparam-form-group hyperparam-form-group--opponent"
      role="group"
      aria-labelledby="hyperparam-form-opponent-title"
    >
      <div className="hyperparam-form-group-header">
        <span
          className="hyperparam-form-group-title"
          id="hyperparam-form-opponent-title"
        >
          Opponent
        </span>
      </div>

      <div
        className="opponent-segmented"
        role="radiogroup"
        aria-labelledby="hyperparam-form-opponent-title"
      >
        {(['bot_ladder', 'self_play'] as const).map(value => {
          const label = value === 'bot_ladder' ? 'Rule-based (L1–L5)' : 'Self-play league'
          const active = mode === value
          return (
            <button
              key={value}
              type="button"
              role="radio"
              aria-checked={active}
              disabled={disabled}
              onClick={() => onModeChange(value)}
              className={`opponent-segmented-option${active ? ' opponent-segmented-option--active' : ''}`}
            >
              {label}
            </button>
          )
        })}
      </div>

      {isSelfPlay && (
        <>
          <fieldset
            className="opponent-sampling"
            aria-label="League sampling strategy"
            disabled={disabled}
          >
            <legend className="opponent-sampling-legend">Sampling</legend>
            {SAMPLING_OPTIONS.map(opt => (
              <label key={opt.value} className="opponent-sampling-option">
                <input
                  type="radio"
                  name="league-sampling"
                  value={opt.value}
                  checked={sampling === opt.value}
                  onChange={() => onSamplingChange(opt.value)}
                />
                <span className="opponent-sampling-label">{opt.label}</span>
                <span className="opponent-sampling-hint">{opt.hint}</span>
              </label>
            ))}
          </fieldset>

          <div className="opponent-pool-row">
            <span
              className="opponent-pool-chip"
              aria-label={`Pool size: ${poolSize ?? 'unknown'} of ${LEAGUE_POOL_CAP}`}
            >
              {`Pool ${poolSize ?? '—'} / ${LEAGUE_POOL_CAP}`}
            </span>
            <span className="opponent-k-factor" title="Elo K annealing (ADR-0014 §2)">
              K = 16 (&lt; 30 games) → 8
            </span>
          </div>

          <p className="opponent-hint">
            Empty pool auto-falls back to rule ladder — submit is never blocked.
          </p>
        </>
      )}
    </div>
  )
}
