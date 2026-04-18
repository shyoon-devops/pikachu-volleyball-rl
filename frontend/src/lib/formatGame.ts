/**
 * Tiny formatters for GameRecord fields rendered in the Recent Games
 * and Replay List tables. Kept in their own module so the React
 * component files stay component-only (react-refresh/only-export-components).
 */

/**
 * Render a bot level cell safely. WS `game:result` broadcasts
 * currently omit `bot_level` (backend/rl/callbacks.py:236-242 →
 * backend/app/ws/handlers.py:357), so a live row may arrive with
 * `undefined`/`null`. Concatenating `"L" + undefined` produced the
 * "L" bug — a bare capital L with nothing after it, which looked like
 * a broken column. Show "L?" instead so the cell is self-describing
 * and the bug is obvious if BE regresses again.
 *
 * Takes `number | null | undefined` (not optional) on purpose so
 * callers have to acknowledge the missing case rather than forgetting.
 */
export function formatBotLevel(level: number | null | undefined): string {
  if (level === null || level === undefined || Number.isNaN(level)) {
    return 'L?'
  }
  return `L${level}`
}

/**
 * Render a rally count cell while distinguishing "BE didn't tell us"
 * from "the game legitimately ended with N rallies".
 *
 * [BE-WAITING] rally_count field required.
 *
 * Today every saved game reads 0 because:
 *   1. `LiveFrameCallback._on_step` enqueues the result dict
 *      WITHOUT a `rally_count` key
 *      (`backend/rl/callbacks.py:284-292`).
 *   2. The handler defaults to 0 when persisting
 *      (`backend/app/ws/handlers.py:341` —
 *      `rally_count=data.get("rally_count", 0)`).
 *   3. The WS broadcast forwards the same payload, so the live FE
 *      row also reads 0.
 *
 * BE needs to track rally crossings (the original engine has no
 * rally counter; one needs to be added — likely incremented on every
 * net-cross detected during a rally, reset on score) and add the
 * field to both the queued dict and the GameRecord schema.
 *
 * Until BE ships that, this helper renders "?" when the field is
 * missing OR 0, so the History column stops claiming "0 rallies"
 * for every game. After BE ships, callers should prefer the
 * non-defensive path: render `g.rallyCount` directly when the
 * field is reliably present.
 */
export function formatRallyCount(count: number | null | undefined): string {
  if (count === null || count === undefined || count === 0 || Number.isNaN(count)) {
    return '?'
  }
  return String(count)
}

/**
 * Average frames-per-rally for a game. Used in the Recent Games
 * column to give an at-a-glance "how long was each rally" reading.
 *
 * Derives from `durationFrames / rallyCount` (rounded). Returns "?"
 * when `rallyCount` is missing/0 (BE-WAITING) so the cell is honest
 * rather than rendering "Infinity" or a misleading "0".
 *
 * Originally this column was going to read raw `avg_rally_length`
 * from BE, but BE doesn't track per-game rally length and tracking
 * `rally_count` itself is still BE-WAITING (see `formatRallyCount`).
 * Deriving on the FE means the column starts working immediately
 * once BE ships the rally counter — no second roundtrip required.
 */
export function formatAvgRallyLength(
  durationFrames: number | null | undefined,
  rallyCount: number | null | undefined,
): string {
  if (
    durationFrames === null || durationFrames === undefined ||
    rallyCount === null || rallyCount === undefined ||
    rallyCount === 0 || Number.isNaN(durationFrames) || Number.isNaN(rallyCount)
  ) {
    return '?'
  }
  return `${Math.round(durationFrames / rallyCount)}f`
}

/**
 * Short-form experiment id for table cells. Full UUID4-style ids
 * are 36 chars and break the table layout — first 8 chars are
 * unique enough for the operator to spot grouping at a glance.
 *
 * Returns "—" when missing so cells stay aligned. The full id is
 * still surfaced in the title attribute by the caller.
 */
export function formatExperimentIdShort(id: string | null | undefined): string {
  if (!id) return '—'
  return id.length > 8 ? id.slice(0, 8) : id
}

/**
 * Render the History page's env chip. ENV 0..15 map to `ENV N`;
 * missing env id renders as an em-dash so the column stays tidy for
 * demo / single-env rows (and for any game saved before BE started
 * emitting the field).
 *
 * Stays a stringly helper (not a React component) so it can sit next
 * to the other formatGame helpers and reuse the same testing setup.
 */
export function formatEnvId(envId: number | null | undefined): string {
  if (envId === null || envId === undefined || Number.isNaN(envId)) {
    return '—'
  }
  return `ENV ${envId}`
}
