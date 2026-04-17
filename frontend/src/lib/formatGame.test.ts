import { describe, it, expect } from 'vitest'
import {
  formatBotLevel,
  formatRallyCount,
  formatAvgRallyLength,
  formatExperimentIdShort,
} from './formatGame'

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

describe('formatRallyCount (BE-WAITING)', () => {
  // Until BE tracks rally crossings, every persisted game has
  // rally_count=0 (handler default). Rendering "0 rallies" would be
  // a lie — switch to "?" so the column reads as "no data" instead
  // of "this game had zero rallies".
  it('renders "?" for undefined (live row from WS broadcast)', () => {
    expect(formatRallyCount(undefined)).toBe('?')
  })

  it('renders "?" for null (defensive — REST shape change)', () => {
    expect(formatRallyCount(null)).toBe('?')
  })

  it('renders "?" for 0 (current BE default — treat as missing)', () => {
    // Once BE actually tracks rallies the helper should be
    // re-evaluated: a legitimate 0-rally game (e.g. single serve win)
    // would also render "?" today. Acceptable trade-off until
    // BE-WAITING is resolved.
    expect(formatRallyCount(0)).toBe('?')
  })

  it('renders "?" for NaN', () => {
    expect(formatRallyCount(Number.NaN)).toBe('?')
  })

  it('renders the integer when BE provides a real count', () => {
    expect(formatRallyCount(7)).toBe('7')
    expect(formatRallyCount(1)).toBe('1')
  })
})

describe('formatAvgRallyLength', () => {
  it('rounds frames/rally to an integer with an "f" suffix', () => {
    expect(formatAvgRallyLength(450, 9)).toBe('50f')
    expect(formatAvgRallyLength(4500, 7)).toBe('643f') // 4500/7 = 642.86 → 643
  })

  it('renders "?" when rallyCount is 0 (BE-WAITING) — avoids Infinity', () => {
    expect(formatAvgRallyLength(4500, 0)).toBe('?')
  })

  it('renders "?" when either input is missing', () => {
    expect(formatAvgRallyLength(undefined, 7)).toBe('?')
    expect(formatAvgRallyLength(4500, undefined)).toBe('?')
    expect(formatAvgRallyLength(null, null)).toBe('?')
  })

  it('renders "?" for NaN inputs', () => {
    expect(formatAvgRallyLength(Number.NaN, 7)).toBe('?')
    expect(formatAvgRallyLength(4500, Number.NaN)).toBe('?')
  })
})

describe('formatExperimentIdShort', () => {
  it('truncates a long id to the first 8 characters', () => {
    expect(formatExperimentIdShort('abcdef1234567890')).toBe('abcdef12')
  })

  it('returns short ids unchanged', () => {
    expect(formatExperimentIdShort('exp-1')).toBe('exp-1')
    expect(formatExperimentIdShort('12345678')).toBe('12345678')
  })

  it('renders "—" when the id is missing', () => {
    expect(formatExperimentIdShort(null)).toBe('—')
    expect(formatExperimentIdShort(undefined)).toBe('—')
    expect(formatExperimentIdShort('')).toBe('—')
  })
})
