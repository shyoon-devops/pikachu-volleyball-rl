import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { getGames } from '../../lib/api'
import type { GameRecord } from '../../lib/types'

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
              ))}
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr>
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
        <div style={{ display: 'flex', justifyContent: 'center', gap: 8, marginTop: 16 }}>
          <button
            onClick={() => setPage(p => Math.max(1, p - 1))}
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
            {page} / {totalPages}
          </span>
          <button
            onClick={() => setPage(p => Math.min(totalPages, p + 1))}
            disabled={page >= totalPages}
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
          >
            Next
          </button>
        </div>
      )}
    </div>
  )
}
