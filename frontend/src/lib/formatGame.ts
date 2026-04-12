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
