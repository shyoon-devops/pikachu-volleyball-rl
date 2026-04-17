import { useState, useEffect, useMemo } from 'react'
import { useNavigate } from 'react-router-dom'
import { getGames, getAvailableReplays } from '../../lib/api'
import type { GameRecord, ReplayInfo } from '../../lib/types'
import { formatBotLevel, formatRallyCount } from '../../lib/formatGame'
import { formatKstDateTime } from '../../lib/formatTime'
import './ReplayList.css'

const PAGE_LIMIT = 20

/**
 * Unified game-history view (B2, 2026-04-18).
 *
 * Previously the page had two parallel surfaces — an "Available
 * Replays" card grid driven by `/api/replays` plus a paginated
 * `/api/games` table — and the user had to mentally join the two by
 * `gameId`. Now both endpoints are fetched in parallel and merged
 * into a single per-row view: each `GameRecord` carries a "Watch"
 * action when a replay file exists for its `id`.
 *
 * Why we still hit both endpoints:
 *   - `/api/games`     — authoritative metadata (timestamp, scores,
 *                        winner, durationFrames, rallyCount, botLevel)
 *   - `/api/replays`   — filesystem inventory (which `gameId`s have a
 *                        playable .msgpack on disk)
 * They live in different stores (Mongo vs filesystem), so no single
 * endpoint can answer "give me games + their replay availability".
 * Two parallel REST calls is cheap.
 *
 * Failure mode: if the replays endpoint fails, we still render games
 * without the Watch column lighting up (no replay link). The error
 * banner only appears for a games-fetch failure, since that's the
 * only data the table can't render around.
 */
export function ReplayList() {
  const navigate = useNavigate()
  const [games, setGames] = useState<GameRecord[]>([])
  const [replays, setReplays] = useState<ReplayInfo[]>([])
  const [page, setPage] = useState(1)
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    // `Promise.all` short-circuits on the first rejection — using
    // `.catch(() => [])` on the replays call lets games still render
    // when the filesystem inventory endpoint hiccups.
    Promise.all([
      getGames(page, PAGE_LIMIT),
      getAvailableReplays().catch(() => [] as ReplayInfo[]),
    ])
      .then(([gamesRes, replaysRes]) => {
        if (cancelled) return
        setGames(gamesRes.data)
        setTotal(gamesRes.total)
        setReplays(replaysRes)
        setError(null)
      })
      .catch(err => {
        if (cancelled) return
        setError(err instanceof Error ? err.message : 'Failed to load games')
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => { cancelled = true }
  }, [page])

  /**
   * Build a `Map<gameId, ReplayInfo>` once per replays change so the
   * per-row lookup in the table body stays O(1). Recomputing inside
   * the row map() would be O(N²) on long pages.
   */
  const replayByGameId = useMemo(() => {
    const m = new Map<string, ReplayInfo>()
    for (const r of replays) m.set(r.gameId, r)
    return m
  }, [replays])

  const totalPages = Math.max(1, Math.ceil(total / PAGE_LIMIT))

  const changePage = (next: number) => {
    setPage(next)
  }

  return (
    <div className="replay-list">
      <h2 className="replay-list-title">Game History</h2>

      {error && (
        <div className="replay-list-error alert-error">{error}</div>
      )}

      <div className="replay-list-table-wrapper card table-scroll">
        <table className="replay-list-table">
          <thead>
            <tr>
              {['Date', 'Bot Level', 'Score', 'Winner', 'Frames', 'Rallies', 'Replay'].map(h => (
                <th key={h} scope="col">{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr>
                <td colSpan={7} className="replay-list-empty">Loading...</td>
              </tr>
            ) : games.length === 0 ? (
              <tr>
                <td colSpan={7} className="replay-list-empty empty-state">No games recorded yet.</td>
              </tr>
            ) : (
              games.map(g => {
                // Join on `gameId` (the UUID4 used as the replay file
                // stem). `g.id` is the Mongo ObjectId hex — unrelated
                // to the replay filename. Falls back to `g.id` only
                // for legacy rows where the UUID was stored as `_id`
                // (pre-port docs); under normal BE this is a no-op.
                const joinKey = g.gameId ?? g.id
                const replay = replayByGameId.get(joinKey)
                return (
                  <tr key={g.id}>
                    <td className="text-muted">
                      {formatKstDateTime(g.timestamp)}
                    </td>
                    <td>{formatBotLevel(g.botLevel)}</td>
                    <td>
                      <span className="score-p1">{g.score1}</span>
                      {' : '}
                      <span className="score-p2">{g.score2}</span>
                    </td>
                    <td className={g.winner === 1 ? 'winner-agent' : 'winner-bot'}>
                      {g.winner === 1 ? 'RL Agent' : 'Bot'}
                    </td>
                    <td className="text-muted">{g.durationFrames}</td>
                    <td className="text-muted">{formatRallyCount(g.rallyCount)}</td>
                    <td>
                      {replay ? (
                        <button
                          type="button"
                          className="replay-list-btn"
                          onClick={() => navigate(`/replay/${joinKey}`)}
                          aria-label={`Watch replay for game ${joinKey.slice(0, 8)}`}
                          title={`${(replay.sizeBytes / 1024).toFixed(0)}KB`}
                        >
                          Watch
                        </button>
                      ) : (
                        <span className="text-muted" aria-label="No replay file available">—</span>
                      )}
                    </td>
                  </tr>
                )
              })
            )}
          </tbody>
        </table>
      </div>

      {totalPages > 1 && (
        <div className="replay-list-pagination">
          <button
            onClick={() => changePage(Math.max(1, page - 1))}
            disabled={page <= 1}
            className="replay-list-page-btn btn btn-ghost"
          >
            Prev
          </button>
          <span className="replay-list-page-info">
            {page} / {totalPages}
          </span>
          <button
            onClick={() => changePage(Math.min(totalPages, page + 1))}
            disabled={page >= totalPages}
            className="replay-list-page-btn btn btn-ghost"
          >
            Next
          </button>
        </div>
      )}
    </div>
  )
}
