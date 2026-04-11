import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { getGames } from '../../lib/api'
import type { GameRecord } from '../../lib/types'
<<<<<<< HEAD
import './ReplayList.css'
=======
>>>>>>> github/yoon/designer

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
<<<<<<< HEAD
    <div className="replay-list">
      <h2 className="replay-list-title">Game History</h2>

      {error && (
        <div className="replay-list-error alert-error">{error}</div>
      )}

      <div className="replay-list-table-wrapper card">
        <table className="replay-list-table">
          <thead>
            <tr>
              {['Date', 'Bot Level', 'Score', 'Winner', 'Frames', 'Rallies', ''].map(h => (
                <th key={h}>{h}</th>
=======
    <div style={{ maxWidth: 1000, margin: '0 auto', padding: 24 }}>
      <h2 style={{ fontSize: 18, color: '#ccc', marginBottom: 16 }}>Game History</h2>

      {error && (
        <div style={{ padding: 12, background: '#3a1a1a', border: '1px solid #5a2a2a', borderRadius: 6, color: '#f87171', fontSize: 13, marginBottom: 16 }}>
          {error}
        </div>
      )}

      <div style={{ background: '#1a1a2e', borderRadius: 8, border: '1px solid #2a2a3e', overflow: 'hidden' }}>
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
          <thead>
            <tr style={{ borderBottom: '1px solid #2a2a3e' }}>
              {['Date', 'Bot Level', 'Score', 'Winner', 'Frames', 'Rallies', ''].map(h => (
                <th key={h} style={{ textAlign: 'left', padding: '10px 14px', color: '#888', fontWeight: 500, fontSize: 12 }}>{h}</th>
>>>>>>> github/yoon/designer
              ))}
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr>
<<<<<<< HEAD
                <td colSpan={7} className="replay-list-empty">Loading...</td>
              </tr>
            ) : games.length === 0 ? (
              <tr>
                <td colSpan={7} className="replay-list-empty">No games recorded yet.</td>
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
                      className="replay-list-btn"
=======
                <td colSpan={7} style={{ padding: 24, textAlign: 'center', color: '#666' }}>Loading...</td>
              </tr>
            ) : games.length === 0 ? (
              <tr>
                <td colSpan={7} style={{ padding: 24, textAlign: 'center', color: '#666' }}>No games recorded yet.</td>
              </tr>
            ) : (
              games.map(g => (
                <tr key={g.id} style={{ borderBottom: '1px solid #1f1f30' }}>
                  <td style={{ padding: '8px 14px', color: '#888' }}>
                    {new Date(g.timestamp).toLocaleString()}
                  </td>
                  <td style={{ padding: '8px 14px' }}>L{g.botLevel}</td>
                  <td style={{ padding: '8px 14px' }}>
                    <span style={{ color: '#ffd700' }}>{g.score1}</span>
                    {' : '}
                    <span style={{ color: '#ff4444' }}>{g.score2}</span>
                  </td>
                  <td style={{ padding: '8px 14px', color: g.winner === 1 ? '#22c55e' : '#ef4444' }}>
                    {g.winner === 1 ? 'RL Agent' : 'Bot'}
                  </td>
                  <td style={{ padding: '8px 14px', color: '#888' }}>{g.durationFrames}</td>
                  <td style={{ padding: '8px 14px', color: '#888' }}>{g.rallyCount}</td>
                  <td style={{ padding: '8px 14px' }}>
                    <button
                      onClick={() => navigate(`/replay/${g.id}`)}
                      style={{
                        padding: '4px 12px',
                        background: '#3b82f6',
                        color: '#fff',
                        border: 'none',
                        borderRadius: 4,
                        fontFamily: 'monospace',
                        fontSize: 11,
                        cursor: 'pointer',
                      }}
>>>>>>> github/yoon/designer
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
<<<<<<< HEAD
        <div className="replay-list-pagination">
          <button
            onClick={() => changePage(Math.max(1, page - 1))}
            disabled={page <= 1}
            className="replay-list-page-btn"
          >
            Prev
          </button>
          <span className="replay-list-page-info">
=======
        <div style={{ display: 'flex', justifyContent: 'center', gap: 8, marginTop: 16 }}>
          <button
            onClick={() => changePage(Math.max(1, page - 1))}
            disabled={page <= 1}
            style={{
              padding: '6px 12px',
              background: '#2a2a3e',
              color: page <= 1 ? '#444' : '#ccc',
              border: 'none',
              borderRadius: 4,
              fontFamily: 'monospace',
              fontSize: 12,
              cursor: page <= 1 ? 'not-allowed' : 'pointer',
            }}
          >
            Prev
          </button>
          <span style={{ padding: '6px 12px', fontSize: 12, color: '#888' }}>
>>>>>>> github/yoon/designer
            {page} / {totalPages}
          </span>
          <button
            onClick={() => changePage(Math.min(totalPages, page + 1))}
            disabled={page >= totalPages}
<<<<<<< HEAD
            className="replay-list-page-btn"
=======
            style={{
              padding: '6px 12px',
              background: '#2a2a3e',
              color: page >= totalPages ? '#444' : '#ccc',
              border: 'none',
              borderRadius: 4,
              fontFamily: 'monospace',
              fontSize: 12,
              cursor: page >= totalPages ? 'not-allowed' : 'pointer',
            }}
>>>>>>> github/yoon/designer
          >
            Next
          </button>
        </div>
      )}
    </div>
  )
}
