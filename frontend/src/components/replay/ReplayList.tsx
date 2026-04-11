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
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const limit = 20

  useEffect(() => {
    setLoading(true)
    setError(null)
    getGames(page, limit)
      .then(res => {
        setGames(res.data)
        setTotal(res.total)
      })
      .catch(err => {
        setError(err instanceof Error ? err.message : 'Failed to load games')
      })
      .finally(() => setLoading(false))
  }, [page])

  const totalPages = Math.max(1, Math.ceil(total / limit))

  return (
    <div className="replay-list">
      <h2 className="replay-list__title">Game History</h2>

      {error && <div className="replay-list__error">{error}</div>}

      <div className="replay-list__table-wrapper">
        <table>
          <thead>
            <tr>
              <th>Date</th>
              <th>Bot Level</th>
              <th>Score</th>
              <th>Winner</th>
              <th>Frames</th>
              <th>Rallies</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr>
                <td colSpan={7} style={{ textAlign: 'center', padding: 'var(--space-6)' }}>
                  <div style={{ display: 'flex', justifyContent: 'center' }}>
                    <div className="spinner spinner-sm" />
                  </div>
                </td>
              </tr>
            ) : games.length === 0 ? (
              <tr>
                <td colSpan={7}>
                  <div className="empty-state">
                    <div className="empty-state-icon">&#128196;</div>
                    <span>No games recorded yet.</span>
                  </div>
                </td>
              </tr>
            ) : (
              games.map(g => (
                <tr key={g.id}>
                  <td className="muted">
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
                  <td className="muted">{g.durationFrames}</td>
                  <td className="muted">{g.rallyCount}</td>
                  <td>
                    <button
                      onClick={() => navigate(`/replay/${g.id}`)}
                      className="btn btn-primary"
                      style={{ padding: '4px 12px' }}
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
        <div className="replay-list__pagination">
          <button
            onClick={() => setPage(p => Math.max(1, p - 1))}
            disabled={page <= 1}
            className="btn btn-ghost"
          >
            Prev
          </button>
          <span className="replay-list__page-info">{page} / {totalPages}</span>
          <button
            onClick={() => setPage(p => Math.min(totalPages, p + 1))}
            disabled={page >= totalPages}
            className="btn btn-ghost"
          >
            Next
          </button>
        </div>
      )}
    </div>
  )
}
