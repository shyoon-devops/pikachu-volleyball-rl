import { describe, it, expect } from 'vitest'
import { render } from '@testing-library/react'
import { ScoreCell } from './ScoreCell'

function renderInTable(s1: number, s2: number) {
  return render(
    <table>
      <tbody>
        <tr>
          <ScoreCell s1={s1} s2={s2} />
        </tr>
      </tbody>
    </table>,
  )
}

describe('ScoreCell (A5.1)', () => {
  it('renders both scores separated by " : " in a single <td>', () => {
    const { container } = renderInTable(15, 12)
    const td = container.querySelector('td.score-cell')
    expect(td).not.toBeNull()
    expect(td?.textContent).toBe('15 : 12')
  })

  it('preserves the per-player class names so the colour rules still apply', () => {
    const { container } = renderInTable(0, 0)
    expect(container.querySelector('span.score-p1')).not.toBeNull()
    expect(container.querySelector('span.score-p2')).not.toBeNull()
  })

  it('renders zero scores literally (not "—")', () => {
    // 0 is a real game state (rally not played yet); the FC-R7E
    // tabular-nums rule must still apply via the .score-cell
    // class and the digit must render verbatim.
    const { container } = renderInTable(0, 0)
    const td = container.querySelector('td.score-cell')
    expect(td?.textContent).toBe('0 : 0')
  })

  it('renders large scores without wrapping (tabular-nums + nowrap via .score-cell)', () => {
    // Sanity check that the wrapper class is applied — the actual
    // CSS rule is exercised by global.css; here we only ensure the
    // hook stays attached to the cell.
    const { container } = renderInTable(99, 100)
    const td = container.querySelector('td.score-cell')
    expect(td).not.toBeNull()
    expect(td?.className).toContain('score-cell')
  })
})
