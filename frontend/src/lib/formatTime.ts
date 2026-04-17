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
 * Format an ISO-8601 timestamp (or a Date) as a KST date+time string.
 * Returns the input string unchanged when it can't be parsed — keeps
 * older / corrupted records from blanking the whole row.
 *
 * Naive-ISO handling (V2 root cause, 2026-04-18): Pydantic serialises
 * `datetime.utcnow()` as `"2026-04-17T17:32:22"` — no `Z`, no offset.
 * JavaScript's `new Date(s)` interprets such bare strings as LOCAL
 * time, so the subsequent KST conversion ran from a wrong base and
 * produced wall-clock-shifted output (the "looks like UTC" symptom
 * the user reported). We preprocess by appending `Z` when the input
 * matches the bare-ISO shape, forcing the parser to treat it as UTC
 * before converting to KST.
 *
 * BE may still emit a string with explicit `Z` or a `±HH:MM` offset
 * (e.g. timeseries timestamps); those bypass the patch.
 *
 * Output shape (matches the historic `toLocaleString` output users
 * expect): `2026. 04. 18. 10:00:00` style via the `ko-KR` locale.
 * We pin the locale too because the user runs Korean dashboards;
 * otherwise CI-rendered snapshots diverge from the deployed UI.
 */
export function formatKstDateTime(value: string | number | Date): string {
  const date =
    value instanceof Date
      ? value
      : new Date(typeof value === 'string' ? coerceNaiveIsoToUtc(value) : value)
  if (Number.isNaN(date.getTime())) {
    return typeof value === 'string' ? value : String(value)
  }
  return new Intl.DateTimeFormat('ko-KR', {
    timeZone: KST_TIME_ZONE,
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false,
  }).format(date)
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
