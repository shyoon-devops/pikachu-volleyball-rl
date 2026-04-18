import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { EnvChip } from './EnvChip'

describe('EnvChip (A5.3)', () => {
  it('renders the formatted env_id with the standard chip class', () => {
    render(<EnvChip envId="3" />)
    const chip = screen.getByLabelText('Env 3')
    expect(chip.className).toContain('env-chip')
    expect(chip.className).not.toContain('env-chip--empty')
    expect(chip.getAttribute('data-env-id')).toBe('3')
  })

  it('handles the demo string env id (parallel-vs-demo distinction)', () => {
    render(<EnvChip envId="demo" />)
    const chip = screen.getByLabelText('Env demo')
    expect(chip.getAttribute('data-env-id')).toBe('demo')
    // BE emits "demo" as a literal id; chip is not the --empty variant.
    expect(chip.className).not.toContain('env-chip--empty')
  })

  it('switches to the --empty variant + alt aria-label when envId is undefined', () => {
    // Pre-extraction sites gated on `=== undefined` (not null) — keep
    // that exact contract so behavior at every call site is byte-equal.
    render(<EnvChip envId={undefined} />)
    const chip = screen.getByLabelText('No env id recorded')
    expect(chip.className).toContain('env-chip--empty')
    expect(chip.getAttribute('data-env-id')).toBe('')
  })

  it('accepts a numeric env id (formatEnvId converts to display)', () => {
    // Type allows number; runtime path delegates to formatEnvId, which
    // returns a stringified value. The aria-label uses the raw input
    // verbatim, so a number renders as such.
    render(<EnvChip envId={5} />)
    expect(screen.getByLabelText('Env 5')).toBeInTheDocument()
  })

  it('null envId still passes the truthy `=== undefined` gate (data-env-id empty)', () => {
    // The pre-extraction sites only checked `=== undefined`, so a null
    // would render the non-empty variant aria-label but the `?? ''`
    // fallback would still empty the data-env-id. Match exactly.
    render(<EnvChip envId={null} />)
    // aria-label says "Env null" because the original ternary did
    // `envId === undefined ? 'No…' : `Env ${envId}``. Behavior preserved.
    expect(screen.getByLabelText('Env null')).toBeInTheDocument()
  })
})
