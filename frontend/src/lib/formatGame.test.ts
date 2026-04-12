import { describe, it, expect } from 'vitest'
import { formatBotLevel } from './formatGame'

describe('formatBotLevel', () => {
  it('renders L1 through L5 for valid levels', () => {
    for (let lvl = 1; lvl <= 5; lvl++) {
      expect(formatBotLevel(lvl)).toBe(`L${lvl}`)
    }
  })

  it('falls back to "L?" for undefined (the Recent Games WS bug)', () => {
    // Regression guard for the "L" label bug (2026-04-12):
    // WS game:result broadcasts omit bot_level, so live rows arrived
    // as { botLevel: undefined }. Previously rendered as "L" —
    // identical to a broken column, no hint that a field was missing.
    expect(formatBotLevel(undefined)).toBe('L?')
  })

  it('falls back to "L?" for null', () => {
    // REST hydration is Pydantic-validated so null shouldn't appear,
    // but defensive: a future schema change shouldn't silently render
    // "Lnull" or "L".
    expect(formatBotLevel(null)).toBe('L?')
  })

  it('falls back to "L?" for NaN', () => {
    // Guards against Number() on a missing/stringy field producing
    // NaN upstream — render shouldn't show "LNaN".
    expect(formatBotLevel(Number.NaN)).toBe('L?')
  })

  it('accepts 0 verbatim (not treated as missing)', () => {
    // 0 is not a legal bot level today (schema is 1-5), but we still
    // want to render whatever the server sent rather than swallow it
    // as "L?" — a visible "L0" surfaces schema drift faster than a
    // silent fallback.
    expect(formatBotLevel(0)).toBe('L0')
  })
})
