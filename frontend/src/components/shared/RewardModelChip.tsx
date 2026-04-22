import { memo } from 'react'
import { parseRewardModel, type RewardModel } from '../../lib/types'
import { t } from '../../lib/i18n'
import './RewardModelChip.css'

/**
 * List-density chip for the reward-model regime (v2.x Sprint 2 —
 * DESIGN-REWARD-MODEL-SELECTOR.md §4).
 *
 * Rendered right of the run title in Recent Games / `/runs` /
 * history lists. The `full` variant (used inside drill-down
 * metadata blocks) drops the chip styling and just renders the
 * long label inline — spec §4 says chips are list-density only.
 *
 * The runtime guard (`parseRewardModel`) means any unknown value
 * coming off the wire falls back to the `shaped_v1` display
 * default rather than rendering a malformed chip. BE always
 * populates the field on `/api/training/runs` (legacy rows are
 * backfilled via migration), so the `null` case should be a
 * BE-bug signal rather than a normal path.
 */
export interface RewardModelChipProps {
  /** Raw value off the wire. `null`/`undefined` → chip degrades to
   *  the `shaped_v1` default per the spec backfill semantics. */
  value: RewardModel | string | null | undefined
  /** `'chip'` (default) — compact uppercase mono pill for list
   *  rows. `'full'` — long label inline (no chip styling), used
   *  inside drill-down metadata blocks. */
  variant?: 'chip' | 'full'
}

/** Chip tone token mapped from the reward-model enum. `shaped` +
 *  `sparse` read as neutral; `learned` borrows the Experimental
 *  tone so the warning colour is consistent with the selector. */
const CHIP_TONE: Record<RewardModel, 'neutral' | 'muted-italic' | 'warning'> = {
  shaped_v1: 'neutral',
  sparse_v1: 'muted-italic',
  learned_shaped_v1: 'warning',
}

/** Full labels for drill-down metadata blocks. */
const FULL_LABEL: Record<RewardModel, string> = {
  shaped_v1: 'Shaped (v1)',
  sparse_v1: 'Sparse',
  learned_shaped_v1: 'Learned shaped',
}

export const RewardModelChip = memo(function RewardModelChip({
  value,
  variant = 'chip',
}: RewardModelChipProps) {
  const parsed = parseRewardModel(value) ?? 'shaped_v1'

  if (variant === 'full') {
    return (
      <span className="reward-model-chip-full" aria-label={`Reward model: ${FULL_LABEL[parsed]}`}>
        {FULL_LABEL[parsed]}
      </span>
    )
  }

  const tone = CHIP_TONE[parsed]
  const text = t(`training.reward_model.chip.${parsed}`)
  return (
    <span
      className={`reward-model-chip reward-model-chip--${tone}`}
      aria-label={`Reward model: ${FULL_LABEL[parsed]}`}
      title={FULL_LABEL[parsed]}
    >
      {text}
    </span>
  )
})
