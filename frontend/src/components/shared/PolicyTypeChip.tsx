import { memo } from 'react'
import { parsePolicyType, RESERVED_POLICY_TYPES, type PolicyType } from '../../lib/types'
import { t } from '../../lib/i18n'
import './PolicyTypeChip.css'

/**
 * List-density chip for the policy-type regime (v2.x Sprint 3 —
 * DESIGN-POLICY-TYPE-SELECTOR.md §4). Sibling to `RewardModelChip`
 * and reuses the same primitive so the two chips stack cleanly in
 * the Recent Games / `/runs` title cell (4 px gap per spec).
 *
 * Rendering rules (§4):
 *   - `mlp_v1`  → neutral (`--color-text-muted`)
 *   - `lstm_v1` → accent (`--color-accent` text; new regime signal)
 *   - `gru_v1` / `transformer_v1` → **reserved**. Trainer rejects
 *     these at start so they're never persisted. If one ever
 *     appears (data drift), the spec asks for a `--color-danger`
 *     chip + "unsupported policy" tooltip rather than silent MLP
 *     fallback. `parsePolicyType` catches unknown strings.
 *
 * The `full` variant renders the long label inline (no chip) for
 * the drill-down metadata block — matches `RewardModelChip`.
 */
export interface PolicyTypeChipProps {
  /** Raw value off the wire. `null` / `undefined` / unknown →
   *  degrades to the `mlp_v1` default per spec backfill rules. */
  value: PolicyType | string | null | undefined
  /** `'chip'` (default) — 9 px uppercase mono pill for list rows.
   *  `'full'` — long label inline (no chip styling), for the
   *  drill-down metadata block. */
  variant?: 'chip' | 'full'
}

/** Tone map. Reserved values get the danger tone *only* when they
 *  leak through a runtime guard — normal-path data will never
 *  hit that branch. */
const CHIP_TONE: Record<PolicyType, 'neutral' | 'accent' | 'danger'> = {
  mlp_v1: 'neutral',
  lstm_v1: 'accent',
  gru_v1: 'danger',
  transformer_v1: 'danger',
}

/** Full labels for drill-down metadata blocks. */
const FULL_LABEL: Record<PolicyType, string> = {
  mlp_v1: 'MLP (v1)',
  lstm_v1: 'LSTM',
  gru_v1: 'GRU',
  transformer_v1: 'Transformer',
}

const RESERVED = new Set<PolicyType>(RESERVED_POLICY_TYPES)

export const PolicyTypeChip = memo(function PolicyTypeChip({
  value,
  variant = 'chip',
}: PolicyTypeChipProps) {
  const parsed = parsePolicyType(value) ?? 'mlp_v1'

  if (variant === 'full') {
    return (
      <span className="policy-type-chip-full" aria-label={`Policy: ${FULL_LABEL[parsed]}`}>
        {FULL_LABEL[parsed]}
      </span>
    )
  }

  const tone = CHIP_TONE[parsed]
  const text = t(`training.policy_type.chip.${parsed}`)
  const reserved = RESERVED.has(parsed)
  return (
    <span
      className={`policy-type-chip policy-type-chip--${tone}`}
      aria-label={reserved ? `Policy: ${FULL_LABEL[parsed]} (unsupported)` : `Policy: ${FULL_LABEL[parsed]}`}
      title={reserved ? 'unsupported policy' : FULL_LABEL[parsed]}
    >
      {text}
    </span>
  )
})
