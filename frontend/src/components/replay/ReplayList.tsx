import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { getGames } from '../../lib/api'
import type { GameRecord } from '../../lib/types'
import './ReplayList.css'

export function ReplayList() {
  const navigate = useNavigate()
  const [games, setGames] = useState<GameRecord[]>([])
  const [page, setPage] = useState(1)
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const limit = 20

  useEffect(() => {
    let cancelled = false
    getGames(page, limit)
      .then(res => {
        if (cancelled) return
        setGames(res.data)
        setTotal(res.total)
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

  const changePage = (next: number) => {
    setLoading(true)
    setPage(next)
  }

  const totalPages = Math.max(1, Math.ceil(total / limit))

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
              {['Date', 'Bot Level', 'Score', 'Winner', 'Frames', 'Rallies', ''].map(h => (
                <th key={h}>{h}</th>
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
              games.map(g => (
                <tr key={g.id}>
                  <td className="text-muted">
                    {new Date(g.timestamp).toLocaleString()}
                  </td>
                  <td>L{g.botLevel}</td>
                  <td>
                    <span className="score-p1">{g.score1}</span>
                    {' : '}
                    <span className="score-p2">{g.score2}</span>
                  </td>
                  <td className={g.winner === 1 ? 'winner-agent' : 'winner-bot'}>
                    {g.winner === 1 ? 'RL Agent' : 'Bot'}
                  </td>
                  <td className="text-muted">{g.durationFrames}</td>
                  <td className="text-muted">{g.rallyCount}</td>
                  <td>
                    <button
                      onClick={() => navigate(`/replay/${g.id}`)}
                      className="replay-list-btn btn btn-primary"
                    >
                      Replay
                    </button>
                  </td>
                </tr>
              ))
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
