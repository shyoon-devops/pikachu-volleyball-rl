import { memo } from 'react'

/**
 * Score cell shared between the Dashboard Recent Games table and
 * the ReplayList unified history (A5 extraction, 2026-04-19). Both
 * surfaces render the exact same `<td class="score-cell">` with
 * two colour-coded spans separated by `:` — extracting keeps one
 * source of truth for the nowrap + tabular-nums rule.
 *
 * CSS comes from `src/styles/global.css` — `.score-cell`,
 * `.score-p1`, `.score-p2`. The extraction carries those class
 * names through verbatim so neither the visual nor the existing
 * FC-R7E nowrap rule changes.
 *
 * `memo` matches the surrounding memoized row components so a
 * parent re-render doesn't repaint this cell when its scalar
 * inputs are unchanged.
 */
export interface ScoreCellProps {
  s1: number
  s2: number
}

export const ScoreCell = memo(function ScoreCell({ s1, s2 }: ScoreCellProps) {
  return (
    <td className="score-cell">
      <span className="score-p1">{s1}</span>
      {' : '}
      <span className="score-p2">{s2}</span>
    </td>
  )
})
