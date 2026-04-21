import { memo } from 'react'
import { parseAlgorithm, type Algorithm } from '../../lib/types'
import { t } from '../../lib/i18n'
import './AlgorithmChip.css'

/**
 * List-density chip for the RL algorithm (v2.x Sprint 5 — the
 * list chip lands in S5, after ADR 0018 extended the enum with
 * `dreamer_v3`). Sibling to `RewardModelChip` / `PolicyTypeChip`
 * — same primitive, same tone vocabulary.
 *
 * Rendering rules:
 *   - `ppo`        → neutral tone (baseline)
 *   - `sac`        → accent tone (signals non-default regime)
 *   - `dreamer_v3` → warning tone (experimental; matches the
 *                    selector's Experimental badge colour)
 *
 * `full` variant renders the long label inline (no chip styling)
 * for the drill-down metadata block.
 */
export interface AlgorithmChipProps {
  /** Raw value off the wire. `null` / `undefined` / unknown →
   *  degrades to the `ppo` default per spec backfill rules. */
  value: Algorithm | string | null | undefined
  /** `'chip'` (default) — 9 px uppercase mono pill for list rows.
   *  `'full'` — long label inline (no chip styling). */
  variant?: 'chip' | 'full'
}

const CHIP_TONE: Record<Algorithm, 'neutral' | 'accent' | 'warning'> = {
  ppo: 'neutral',
  sac: 'accent',
  dreamer_v3: 'warning',
}

const FULL_LABEL: Record<Algorithm, string> = {
  ppo: 'PPO',
  sac: 'SAC',
  dreamer_v3: 'Dreamer V3',
}

export const AlgorithmChip = memo(function AlgorithmChip({
  value,
  variant = 'chip',
}: AlgorithmChipProps) {
  const parsed = parseAlgorithm(value) ?? 'ppo'

  if (variant === 'full') {
    return (
      <span className="algorithm-chip-full" aria-label={`Algorithm: ${FULL_LABEL[parsed]}`}>
        {FULL_LABEL[parsed]}
      </span>
    )
  }

  const tone = CHIP_TONE[parsed]
  const text = t(`training.algorithm.chip.${parsed}`)
  return (
    <span
      className={`algorithm-chip algorithm-chip--${tone}`}
      aria-label={`Algorithm: ${FULL_LABEL[parsed]}`}
      title={FULL_LABEL[parsed]}
    >
      {text}
    </span>
  )
})
