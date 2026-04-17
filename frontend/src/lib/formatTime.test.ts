import { describe, it, expect } from 'vitest'
import { formatKstDateTime, KST_TZ } from './formatTime'

describe('formatKstDateTime', () => {
  it('renders a UTC ISO timestamp in Asia/Seoul (UTC+9) as YYYY-MM-DD HH:mm:ss', () => {
    // 2026-04-18T01:00:00Z → 2026-04-18 10:00:00 KST.
    expect(formatKstDateTime('2026-04-18T01:00:00Z')).toBe('2026-04-18 10:00:00')
  })

  it('emits NO leading whitespace (R2 regression guard, 2026-04-18)', () => {
    // The pre-R2 ko-KR formatter returned " 2026. 04. 18. ..." with a
    // 0x20 prefix that the user perceived as a "gray first character"
    // because the invisible space took up render width inside the
    // Recent Games table cell. Lock this in: every byte must be a
    // digit, dash, colon, or single inter-segment space.
    const out = formatKstDateTime('2026-04-18T01:00:00Z')
    expect(out).toMatch(/^\d/)
    expect(out).not.toMatch(/^\s/)
    expect(out).toMatch(/^[\d\- :]+$/)
  })

  it('shifts a midnight-UTC timestamp into the next KST day', () => {
    // 2026-04-17T23:30:00Z → 2026-04-18 08:30:00 KST.
    expect(formatKstDateTime('2026-04-17T23:30:00Z')).toBe('2026-04-18 08:30:00')
  })

  it('accepts a Date object directly', () => {
    const d = new Date('2026-04-18T01:00:00Z')
    expect(formatKstDateTime(d)).toBe('2026-04-18 10:00:00')
  })

  it('returns the original string when the input cannot be parsed', () => {
    expect(formatKstDateTime('not-a-date')).toBe('not-a-date')
  })

  it('exports the KST IANA name for callers building their own formatter', () => {
    expect(KST_TZ).toBe('Asia/Seoul')
  })

  // V2 root-cause regression guards: BE serialises `datetime.utcnow()`
  // as a naive ISO string ("2026-04-17T17:32:22") with NO timezone
  // suffix, which JS would otherwise parse as local-time. We force-tag
  // these as UTC before the KST conversion.
  it('treats a naive ISO timestamp (no Z) as UTC, not local-time', () => {
    // 2026-04-17T17:32:22 → 2026-04-18 02:32:22 KST (+9 hours).
    expect(formatKstDateTime('2026-04-17T17:32:22')).toBe('2026-04-18 02:32:22')
  })

  it('handles naive ISO with fractional seconds', () => {
    // BE may include microseconds: "2026-04-17T17:32:22.123456".
    expect(formatKstDateTime('2026-04-17T17:32:22.500000')).toBe('2026-04-18 02:32:22')
  })

  it('does NOT modify a string that already carries an offset', () => {
    // Tagged with explicit Z → parsed normally, same KST result.
    const fromZ = formatKstDateTime('2026-04-17T17:32:22Z')
    const fromNaive = formatKstDateTime('2026-04-17T17:32:22')
    expect(fromZ).toBe(fromNaive)
  })

  it('does NOT modify a string with explicit ±HH:MM offset', () => {
    // 2026-04-17T20:32:22+03:00 = 17:32:22Z = 02:32:22 KST.
    expect(formatKstDateTime('2026-04-17T20:32:22+03:00')).toBe('2026-04-18 02:32:22')
  })

  it('produces the canonical YYYY-MM-DD HH:mm:ss shape exactly', () => {
    // Pin the byte-exact output so future refactors can't reintroduce
    // dot separators or whitespace padding.
    expect(formatKstDateTime('2026-04-18T01:00:00Z')).toBe('2026-04-18 10:00:00')
  })
})
