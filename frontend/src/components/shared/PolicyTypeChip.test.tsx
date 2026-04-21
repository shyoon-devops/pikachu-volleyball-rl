import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { PolicyTypeChip } from './PolicyTypeChip'

/**
 * Shared chip contract tests (v2.x Sprint 3 —
 * DESIGN-POLICY-TYPE-SELECTOR.md §4). Covers the four enum
 * values, the `full` variant, the unknown-value fallback (spec
 * §4 — `parsePolicyType` rejects → mlp_v1 default), and the
 * data-drift behaviour for reserved values that leak through.
 */
describe('PolicyTypeChip', () => {
  it('renders the compact chip for mlp_v1 with neutral tone', () => {
    const { container } = render(<PolicyTypeChip value="mlp_v1" />)
    const chip = screen.getByText('mlp')
    expect(chip).toBeInTheDocument()
    expect(chip.getAttribute('aria-label')).toBe('Policy: MLP (v1)')
    expect(container.querySelector('.policy-type-chip--neutral')).not.toBeNull()
  })

  it('renders the lstm chip with accent tone', () => {
    const { container } = render(<PolicyTypeChip value="lstm_v1" />)
    expect(screen.getByText('lstm')).toBeInTheDocument()
    expect(container.querySelector('.policy-type-chip--accent')).not.toBeNull()
  })

  it('renders reserved values (data drift) with danger tone + unsupported label', () => {
    const { container } = render(<PolicyTypeChip value="gru_v1" />)
    expect(container.querySelector('.policy-type-chip--danger')).not.toBeNull()
    const chip = screen.getByText('gru')
    expect(chip.getAttribute('aria-label')).toBe('Policy: GRU (unsupported)')
    expect(chip.getAttribute('title')).toBe('unsupported policy')
  })

  it('full variant renders the long label without chip styling', () => {
    render(<PolicyTypeChip value="lstm_v1" variant="full" />)
    const el = screen.getByText('LSTM')
    expect(el.classList.contains('policy-type-chip-full')).toBe(true)
    expect(el.classList.contains('policy-type-chip')).toBe(false)
  })

  it('falls back to mlp_v1 when the value is unknown', () => {
    render(<PolicyTypeChip value={'bogus' as unknown as string} />)
    expect(screen.getByText('mlp')).toBeInTheDocument()
  })

  it('falls back to mlp_v1 when the value is null', () => {
    render(<PolicyTypeChip value={null} />)
    expect(screen.getByText('mlp')).toBeInTheDocument()
  })
})
