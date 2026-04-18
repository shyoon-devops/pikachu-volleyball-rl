import { describe, it, expect } from 'vitest'
import { render } from '@testing-library/react'
import { TimestampText } from './TimestampText'

describe('TimestampText (A5.2)', () => {
  it('renders the formatted KST timestamp when ts is a valid ISO string', () => {
    const { container } = render(<TimestampText ts="2026-04-17T10:00:00Z" />)
    // The exact format is owned by lib/formatTime; assert the year + a
    // separator are present so this test stays robust to minor format
    // tweaks while still guarding the "renders something" branch.
    expect(container.textContent).toMatch(/2026/)
    expect(container.textContent ?? '').not.toBe('—')
  })

  it('renders an em-dash when ts is null', () => {
    const { container } = render(<TimestampText ts={null} />)
    expect(container.textContent).toBe('—')
  })

  it('renders an em-dash when ts is undefined', () => {
    const { container } = render(<TimestampText ts={undefined} />)
    expect(container.textContent).toBe('—')
  })

  it('renders an em-dash when ts is the empty string (treated as missing)', () => {
    // The component uses a truthy guard, so '' triggers the em-dash
    // branch — that matches the prior inline ternary every call site
    // shipped before the extraction, so the behavior is preserved.
    const { container } = render(<TimestampText ts="" />)
    expect(container.textContent).toBe('—')
  })

  it('does not introduce a wrapping element (Fragment render)', () => {
    // Behaviour-preservation guard: callers retain ownership of the
    // surrounding <td> / <dd> / <span>. A wrapping element here would
    // shift CSS selectors at every call site.
    const { container } = render(
      <span data-testid="parent"><TimestampText ts={null} /></span>,
    )
    const parent = container.querySelector('[data-testid="parent"]')
    expect(parent?.children.length).toBe(0) // Fragment → text node only
    expect(parent?.textContent).toBe('—')
  })
})
