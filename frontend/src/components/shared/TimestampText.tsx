import { formatKstDateTime } from '../../lib/formatTime'

/**
 * KST timestamp text with em-dash fallback for null/undefined input
 * (A5 extraction, 2026-04-19). Six call sites repeated the
 * `ts ? formatKstDateTime(ts) : '—'` ternary inline; this thin
 * helper centralises the fallback so a future format-or-null change
 * only needs to land here.
 *
 * Renders as a Fragment (no wrapping element) so callers retain
 * full control of the parent (`<td>`, `<dd>`, `<span>`, etc.) and
 * the existing `text-muted` class assignments stay where they were.
 * That keeps the rendered DOM byte-equivalent to the pre-extraction
 * markup at every call site — no extra nodes, no shifted CSS
 * selectors.
 */
export interface TimestampTextProps {
  ts: string | null | undefined
}

export function TimestampText({ ts }: TimestampTextProps) {
  return <>{ts ? formatKstDateTime(ts) : '—'}</>
}
