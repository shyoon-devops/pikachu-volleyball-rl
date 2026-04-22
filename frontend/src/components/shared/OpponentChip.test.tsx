import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { OpponentChip } from './OpponentChip'

describe('OpponentChip (v2.x S1)', () => {
  it('renders the rule-bot fallback with the bot level', () => {
    render(<OpponentChip botLevel={3} />)
    const chip = screen.getByLabelText('Opponent: Rule L3')
    expect(chip).toBeInTheDocument()
    expect(chip.className).toContain('opponent-chip--rule')
    expect(chip.className).not.toContain('opponent-chip--policy')
    expect(chip.textContent).toBe('Rule L3')
  })

  it('renders "Rule ?" when bot level is missing', () => {
    render(<OpponentChip />)
    expect(screen.getByLabelText('Opponent: Rule ?')).toBeInTheDocument()
  })

  it('renders the self-play chip when opponentCheckpointId is present', () => {
    render(<OpponentChip opponentCheckpointId="run-baseline__abc12345__200000" botLevel={3} />)
    const chip = screen.getByLabelText(/Opponent: checkpoint run-baseline__abc12345__200000/)
    expect(chip.className).toContain('opponent-chip--policy')
    expect(chip.textContent).toBe('policy_abc12345_200000')
    // Full id exposed via title for hover.
    expect(chip.getAttribute('title')).toBe('run-baseline__abc12345__200000')
  })

  it('falls back to the rule variant when opponentCheckpointId is null', () => {
    // BE-WAITING null branch — treat null the same as missing.
    render(<OpponentChip opponentCheckpointId={null} botLevel={2} />)
    expect(screen.getByLabelText('Opponent: Rule L2')).toBeInTheDocument()
  })

  it('displays the full id when the slug has no double-underscore separator (legacy)', () => {
    // Legacy rows have `{exp_id}/final` stems — no `__` segments.
    render(<OpponentChip opponentCheckpointId="exp-123/final" botLevel={1} />)
    expect(screen.getByText('policy_exp-123/final')).toBeInTheDocument()
  })
})
