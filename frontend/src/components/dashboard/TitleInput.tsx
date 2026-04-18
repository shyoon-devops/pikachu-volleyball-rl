import { useEffect, useId, useRef, useState } from 'react'
import { getTrainingTitles, type TrainingTitleInfo } from '../../lib/api'
import './TitleInput.css'

/**
 * Training-title input that sits above the Basic hyperparam group.
 *
 * Designer spec: docs/DESIGN-TRAINING-TITLE.md §1 (rev 1bc882ab —
 * empty is allowed, BE auto-generates; only user-typed invalid
 * values block submit). BE endpoint: `GET /api/training/titles?q=...`
 * (T1, commit a7351e57).
 *
 * Validation:
 *   - empty / whitespace-only → treated as empty (auto-gen path,
 *     no error, submit allowed)
 *   - length > 60                  → `Max 60 characters` (block submit)
 *   - duplicate (user-typed match) → `Title already in use` (block)
 *
 * Debounced uniqueness check (300 ms) via the titles endpoint. The
 * FE compares case-insensitively against returned titles; if BE
 * isn't reachable / returns an empty list, duplicate check degrades
 * to "no conflict detected" rather than blocking submit — user
 * still gets the server-side uniqueness enforcement on save.
 */

const MAX_LEN = 60
const DEBOUNCE_MS = 300

export type TitleValidationState =
  | { kind: 'ok' }
  | { kind: 'tooLong' }
  | { kind: 'duplicate'; priorStartedAt: string | null }
  | { kind: 'checking' }

interface TitleInputProps {
  /** Controlled value. */
  value: string
  /** Fires on every keystroke. */
  onChange: (next: string) => void
  /** Disable the input (e.g. while training is running). */
  disabled: boolean
  /** Reports validation state up so the parent can gate Start. */
  onValidationChange: (state: TitleValidationState) => void
}

export function TitleInput({
  value,
  onChange,
  disabled,
  onValidationChange,
}: TitleInputProps) {
  const fieldId = useId()
  const hintId = `${fieldId}-hint`
  const errorId = `${fieldId}-error`
  const counterId = `${fieldId}-counter`

  const trimmed = value.trim()
  const isEmpty = trimmed === ''
  const isTooLong = value.length > MAX_LEN

  // Local validation state — the debounced duplicate check overlays
  // the synchronous length check.
  const [state, setState] = useState<TitleValidationState>({ kind: 'ok' })

  /** Latest version counter so out-of-order fetches can be ignored. */
  const fetchSeqRef = useRef(0)
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  useEffect(() => {
    // Sync-first: length check wins over an in-flight dup check so a
    // user typing past 60 sees the error immediately.
    if (isTooLong) {
      setState({ kind: 'tooLong' })
      return
    }
    // Empty is a valid submit path — skip the dup check entirely.
    if (isEmpty) {
      setState({ kind: 'ok' })
      return
    }

    // Debounced duplicate check for non-empty values.
    setState({ kind: 'checking' })
    const mySeq = ++fetchSeqRef.current
    if (debounceRef.current) clearTimeout(debounceRef.current)
    debounceRef.current = setTimeout(async () => {
      try {
        const hits = await getTrainingTitles(trimmed, 20)
        if (mySeq !== fetchSeqRef.current) return // superseded
        const match = hits.find(
          (h: TrainingTitleInfo) => h.title.toLowerCase() === trimmed.toLowerCase(),
        )
        if (match) {
          setState({ kind: 'duplicate', priorStartedAt: match.startedAt ?? null })
        } else {
          setState({ kind: 'ok' })
        }
      } catch {
        // BE unreachable / titles endpoint not deployed → don't block
        // submit. Server-side uniqueness still enforces on save.
        if (mySeq !== fetchSeqRef.current) return
        setState({ kind: 'ok' })
      }
    }, DEBOUNCE_MS)

    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current)
    }
  }, [trimmed, isEmpty, isTooLong])

  // Bubble state changes up.
  useEffect(() => {
    onValidationChange(state)
  }, [state, onValidationChange])

  // Describe-by string for accessibility.
  const describedBy = [
    hintId,
    state.kind === 'tooLong' || state.kind === 'duplicate' ? errorId : null,
    isEmpty ? null : counterId,
  ]
    .filter(Boolean)
    .join(' ')

  return (
    <div className="title-input-field">
      <label className="title-input-label" htmlFor={fieldId}>
        Title
      </label>
      <input
        id={fieldId}
        className={`title-input${state.kind === 'tooLong' || state.kind === 'duplicate' ? ' title-input--invalid' : ''}`}
        type="text"
        maxLength={MAX_LEN + 40 /* slack over the hard cap so we can show "Max 60 characters" rather than silently truncate */}
        placeholder="e.g. my-run-baseline"
        value={value}
        onChange={e => onChange(e.target.value)}
        disabled={disabled}
        aria-describedby={describedBy || undefined}
        aria-invalid={state.kind === 'tooLong' || state.kind === 'duplicate'}
      />
      <p id={hintId} className="title-input-hint">
        Leave blank for an auto-generated name, or type your own.
      </p>
      {!isEmpty && (
        <span
          id={counterId}
          className={`title-input-counter${value.length >= MAX_LEN ? ' title-input-counter--over' : ''}`}
          aria-live="polite"
        >
          {value.length} / {MAX_LEN}
        </span>
      )}
      {state.kind === 'checking' && !isEmpty && (
        <span className="title-input-checking" aria-label="Checking availability">
          …
        </span>
      )}
      {state.kind === 'tooLong' && (
        <span id={errorId} className="title-input-error" role="alert">
          Max 60 characters
        </span>
      )}
      {state.kind === 'duplicate' && (
        <span id={errorId} className="title-input-error" role="alert">
          Title already in use
          {state.priorStartedAt && (
            <span className="title-input-error-sub">
              {' · '}previous run: {new Date(state.priorStartedAt).toLocaleDateString('en-US')}
            </span>
          )}
        </span>
      )}
    </div>
  )
}
