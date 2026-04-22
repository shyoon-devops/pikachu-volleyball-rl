import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { AlgorithmChip } from './AlgorithmChip'

/**
 * Algorithm chip contract tests (v2.x Sprint 5 — ADR 0018
 * extended the enum with `dreamer_v3`). Covers the three
 * recognised enums + the `full` variant + unknown fallback.
 */
describe('AlgorithmChip', () => {
  it('renders the compact ppo chip with neutral tone', () => {
    const { container } = render(<AlgorithmChip value="ppo" />)
    const chip = screen.getByText('ppo')
    expect(chip).toBeInTheDocument()
    expect(chip.getAttribute('aria-label')).toBe('Algorithm: PPO')
    expect(container.querySelector('.algorithm-chip--neutral')).not.toBeNull()
  })

  it('renders the sac chip with accent tone', () => {
    const { container } = render(<AlgorithmChip value="sac" />)
    expect(screen.getByText('sac')).toBeInTheDocument()
    expect(container.querySelector('.algorithm-chip--accent')).not.toBeNull()
  })

  it('renders the dreamer_v3 chip with warning tone + short label', () => {
    const { container } = render(<AlgorithmChip value="dreamer_v3" />)
    const chip = screen.getByText('dreamer')
    expect(chip).toBeInTheDocument()
    expect(chip.getAttribute('aria-label')).toBe('Algorithm: Dreamer V3')
    expect(container.querySelector('.algorithm-chip--warning')).not.toBeNull()
  })

  it('full variant renders the long label without chip styling', () => {
    render(<AlgorithmChip value="dreamer_v3" variant="full" />)
    const el = screen.getByText('Dreamer V3')
    expect(el.classList.contains('algorithm-chip-full')).toBe(true)
    expect(el.classList.contains('algorithm-chip')).toBe(false)
  })

  it('falls back to ppo when the value is unknown or null', () => {
    render(<AlgorithmChip value={'bogus' as unknown as string} />)
    expect(screen.getByText('ppo')).toBeInTheDocument()
  })

  it('falls back to ppo when the value is null', () => {
    render(<AlgorithmChip value={null} />)
    expect(screen.getByText('ppo')).toBeInTheDocument()
  })
})
