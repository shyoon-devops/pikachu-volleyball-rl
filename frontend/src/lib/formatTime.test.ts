import { describe, it, expect } from 'vitest'
import { formatKstDateTime, KST_TZ } from './formatTime'

describe('formatKstDateTime', () => {
  it('renders a UTC ISO timestamp in Asia/Seoul (UTC+9)', () => {
    // 2026-04-18T01:00:00Z → 2026-04-18 10:00:00 KST.
    const out = formatKstDateTime('2026-04-18T01:00:00Z')
    // Defensive substring matching: ko-KR formatter inserts "년/월/일"
    // separators on some Node versions; we just check the salient
    // numbers are present and the leading digits are KST values.
    expect(out).toMatch(/2026/)
    expect(out).toMatch(/04/)
    expect(out).toMatch(/18/)
    expect(out).toMatch(/10:00:00/)
  })

  it('shifts a midnight-UTC timestamp into the next KST day', () => {
    // 2026-04-17T23:30:00Z → 2026-04-18 08:30:00 KST.
    const out = formatKstDateTime('2026-04-17T23:30:00Z')
    expect(out).toMatch(/2026/)
    expect(out).toMatch(/18/)
    expect(out).toMatch(/08:30:00/)
  })

  it('accepts a Date object directly', () => {
    const d = new Date('2026-04-18T01:00:00Z')
    const out = formatKstDateTime(d)
    expect(out).toMatch(/10:00:00/)
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
    const out = formatKstDateTime('2026-04-17T17:32:22')
    expect(out).toMatch(/2026/)
    expect(out).toMatch(/18/)
    expect(out).toMatch(/02:32:22/)
  })

  it('handles naive ISO with fractional seconds', () => {
    // BE may include microseconds: "2026-04-17T17:32:22.123456".
    const out = formatKstDateTime('2026-04-17T17:32:22.500000')
    expect(out).toMatch(/02:32:22/)
  })

  it('does NOT modify a string that already carries an offset', () => {
    // Tagged with explicit Z → parsed normally, same KST result.
    const fromZ = formatKstDateTime('2026-04-17T17:32:22Z')
    const fromNaive = formatKstDateTime('2026-04-17T17:32:22')
    expect(fromZ).toBe(fromNaive)
  })

  it('does NOT modify a string with explicit ±HH:MM offset', () => {
    // 2026-04-17T20:32:22+03:00 = 17:32:22Z = 02:32:22 KST.
    const out = formatKstDateTime('2026-04-17T20:32:22+03:00')
    expect(out).toMatch(/02:32:22/)
  })
})
