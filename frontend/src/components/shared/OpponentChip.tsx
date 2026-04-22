import { memo } from 'react'
import './OpponentChip.css'

/**
 * Opponent chip for the Recent Games Opponent column (v2.x Sprint 1
 * — docs/design/SELF-PLAY-UX.md §3).
 *
 * Renders one of two variants depending on the data available:
 *   - Rule-bot matches (the v1 path, and every game today): show
 *     `Rule L{botLevel}` against the neutral `--color-bg-elevated`
 *     background.
 *   - Self-play matches (when BE ships
 *     `GameRecord.opponent_checkpoint_id`): show a truncated
 *     `policy_<exp8>_<step>` chip against `--color-accent-dim` so
 *     the column tells the two modes apart at a glance.
 *
 * The checkpoint id comes in as the full league slug
 * (`run-baseline__abc12345__200000`); we trim to the last two
 * `__`-separated segments (the exp8 hash + step) to fit the column
 * width while preserving the useful identity bits. Full id is
 * exposed via the `title` attribute for hover.
 */
export interface OpponentChipProps {
  /** Opponent checkpoint id (league slug). `null`/`undefined` means
   *  rule-bot — fall back to the `botLevel` variant. */
  opponentCheckpointId?: string | null
  /** Rule-bot level (1–5). Used for the fallback variant. `undefined`
   *  means BE never set it — render `Rule ?`. */
  botLevel?: number
}

export const OpponentChip = memo(function OpponentChip({
  opponentCheckpointId,
  botLevel,
}: OpponentChipProps) {
  if (opponentCheckpointId) {
    const short = shortCheckpoint(opponentCheckpointId)
    return (
      <span
        className="opponent-chip opponent-chip--policy"
        title={opponentCheckpointId}
        aria-label={`Opponent: checkpoint ${opponentCheckpointId}`}
      >
        {`policy_${short}`}
      </span>
    )
  }
  const levelLabel = typeof botLevel === 'number' ? `L${botLevel}` : '?'
  return (
    <span
      className="opponent-chip opponent-chip--rule"
      aria-label={`Opponent: Rule ${levelLabel}`}
    >
      {`Rule ${levelLabel}`}
    </span>
  )
})

function shortCheckpoint(id: string): string {
  const parts = id.split('__')
  if (parts.length >= 2) return parts.slice(-2).join('_')
  return id
}
