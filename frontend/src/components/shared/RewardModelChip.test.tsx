import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { RewardModelChip } from './RewardModelChip'

/**
 * Shared chip contract tests (v2.x Sprint 2 —
 * DESIGN-REWARD-MODEL-SELECTOR.md §4). Covers the three
 * recognised enums, the `full` variant, and the unknown-value
 * fallback demanded by spec §9 (FE rejects unknown → renders the
 * `shaped_v1` default).
 */
describe('RewardModelChip', () => {
  it('renders the compact chip for a known value', () => {
    render(<RewardModelChip value="sparse_v1" />)
    const chip = screen.getByText('sparse')
    expect(chip).toBeInTheDocument()
    expect(chip.getAttribute('aria-label')).toBe('Reward model: Sparse')
  })

  it('renders the learned variant with warning tone', () => {
    const { container } = render(<RewardModelChip value="learned_shaped_v1" />)
    expect(screen.getByText('learned')).toBeInTheDocument()
    const chip = container.querySelector('.reward-model-chip--warning')
    expect(chip).not.toBeNull()
  })

  it('full variant renders the long label without chip styling', () => {
    render(<RewardModelChip value="shaped_v1" variant="full" />)
    const el = screen.getByText('Shaped (v1)')
    expect(el.classList.contains('reward-model-chip-full')).toBe(true)
    expect(el.classList.contains('reward-model-chip')).toBe(false)
  })

  it('falls back to shaped_v1 when the value is unknown/null (spec §9 guard)', () => {
    render(<RewardModelChip value={'bogus-enum' as unknown as string} />)
    expect(screen.getByText('shaped')).toBeInTheDocument()
  })

  it('falls back to shaped_v1 when the value is null', () => {
    render(<RewardModelChip value={null} />)
    expect(screen.getByText('shaped')).toBeInTheDocument()
  })
})
