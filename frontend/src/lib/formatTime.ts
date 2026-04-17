/**
 * Time formatters that pin output to the Asia/Seoul (KST) timezone.
 *
 * BE serialises `timestamp` as ISO-8601 UTC strings
 * (`backend/rl/callbacks.py` enqueues `datetime.utcnow().isoformat()`),
 * but `Date.prototype.toLocaleString()` defaults to the user's local
 * timezone. On any browser whose system clock is set elsewhere — CI
 * containers (UTC), users on a VPN, dev machines on travel — the
 * History page rendered times that didn't match what the operator
 * remembered seeing in the dashboard, which always shows live KST
 * values.
 *
 * Forcing Asia/Seoul is the simplest fix: every operator on this
 * project is in KR and reads timestamps as KST. If the team becomes
 * multi-timezone we can add a per-user setting later — until then,
 * ambient `toLocaleString()` is the only consumer mismatch worth
 * eliminating.
 */

const KST_TIME_ZONE = 'Asia/Seoul'

/**
 * Format an ISO-8601 timestamp (or a Date) as a KST date+time string
 * in the canonical `YYYY-MM-DD HH:mm:ss` shape.
 *
 * Returns the input string unchanged when it can't be parsed — keeps
 * older / corrupted records from blanking the whole row.
 *
 * Naive-ISO handling (V2 root cause, 2026-04-18): Pydantic serialises
 * `datetime.utcnow()` as `"2026-04-17T17:32:22"` — no `Z`, no offset.
 * JavaScript's `new Date(s)` interprets such bare strings as LOCAL
 * time, so the subsequent KST conversion ran from a wrong base and
 * produced wall-clock-shifted output. We preprocess by appending `Z`
 * when the input matches the bare-ISO shape (`coerceNaiveIsoToUtc`).
 *
 * Output shape (R2 fix, 2026-04-18): direct ISO `YYYY-MM-DD HH:mm:ss`
 * built from `Intl.DateTimeFormat.formatToParts`. The previous
 * `format()` route on `'ko-KR'` returned `" 2026. 04. 18. 02:32:22"`
 * — a LEADING SPACE (charcode 0x20) followed by dot-separated dates.
 * The hidden whitespace is what the user perceived as a "gray first
 * character" — it shifted the visible "2" rightward inside the table
 * cell while taking color from the background. Building the string
 * manually from parts gives us total control: no leading whitespace,
 * uniform separators, and the same character class (digits + `-` /
 * `:` / single space) end-to-end so the rendered text is one solid
 * color block.
 */
export function formatKstDateTime(value: string | number | Date): string {
  const date =
    value instanceof Date
      ? value
      : new Date(typeof value === 'string' ? coerceNaiveIsoToUtc(value) : value)
  if (Number.isNaN(date.getTime())) {
    return typeof value === 'string' ? value : String(value)
  }
  const parts = new Intl.DateTimeFormat('en-CA', {
    timeZone: KST_TIME_ZONE,
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false,
  }).formatToParts(date)

  // Pull each part by `.type` so format-string drift on platforms
  // (some Node versions reorder literals) can't shift the assembly.
  // `en-CA` is the cleanest 24-hour locale that Intl gives us — it
  // reliably emits 2-digit components without locale punctuation.
  const get = (type: Intl.DateTimeFormatPartTypes): string =>
    parts.find(p => p.type === type)?.value ?? ''

  // Manual `00` fallback only kicks in if a platform omits `hour` at
  // midnight (rare bug). Keeps the shape consistent.
  const hh = (get('hour') || '00') === '24' ? '00' : (get('hour') || '00')
  return `${get('year')}-${get('month')}-${get('day')} ${hh}:${get('minute')}:${get('second')}`
}

/**
 * Detect a bare ISO-8601 datetime (no `Z`, no `±HH:MM`) and append
 * `Z` so it parses as UTC. Strings that already carry a timezone
 * suffix are returned unchanged. Strings that don't look like ISO
 * datetimes at all are also returned as-is — `new Date()` will still
 * return Invalid Date and the caller falls through to the
 * unchanged-string branch above.
 */
function coerceNaiveIsoToUtc(s: string): string {
  // ISO-8601 datetime, optional fractional seconds, NO trailing tz.
  // ^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(:\d{2}(\.\d+)?)?$
  if (/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(:\d{2}(\.\d+)?)?$/.test(s)) {
    return `${s}Z`
  }
  return s
}

/**
 * KST timezone identifier exposed for cases where a caller needs it
 * directly (e.g. building their own DateTimeFormat with a custom
 * shape). Prefer `formatKstDateTime` for the standard table output.
 */
export const KST_TZ = KST_TIME_ZONE
