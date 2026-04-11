import { useState, useEffect } from 'react'
import { getModels, getEvalResults, runEvaluation } from '../../lib/api'
import { EvalChart } from './EvalChart'
import type { ModelInfo, EvalResult } from '../../lib/types'

const btnStyle: React.CSSProperties = {
  padding: '8px 16px',
  border: 'none',
  borderRadius: 6,
  fontFamily: 'monospace',
  fontSize: 13,
  fontWeight: 600,
  cursor: 'pointer',
}

const fieldStyle: React.CSSProperties = {
  padding: '6px 8px',
  background: '#0f0f1a',
  border: '1px solid #3a3a5e',
  borderRadius: 4,
  color: '#e0e0e0',
  fontFamily: 'monospace',
  fontSize: 12,
}

export function EvalPanel() {
  const [models, setModels] = useState<ModelInfo[]>([])
  const [results, setResults] = useState<EvalResult[]>([])
  const [selectedModel, setSelectedModel] = useState('')
  const [botLevel, setBotLevel] = useState(1)
  const [nGames, setNGames] = useState(50)
  const [filterLevel, setFilterLevel] = useState<number | null>(null)
  const [loading, setLoading] = useState(false)
  const [running, setRunning] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    setLoading(true)
    Promise.all([getModels(), getEvalResults()])
      .then(([m, r]) => {
        setModels(m)
        setResults(r)
        if (m.length > 0) setSelectedModel(m[0].path)
      })
      .catch(err => setError(err instanceof Error ? err.message : 'Failed to load data'))
      .finally(() => setLoading(false))
  }, [])

  const handleRun = () => {
    if (!selectedModel) return
    setRunning(true)
    setError(null)
    runEvaluation(selectedModel, botLevel, nGames)
      .then(() => getEvalResults())
      .then(r => setResults(r))
      .catch(err => setError(err instanceof Error ? err.message : 'Evaluation failed'))
      .finally(() => setRunning(false))
  }

  if (loading) {
    return <div style={{ padding: 24, textAlign: 'center', color: '#888' }}>Loading...</div>
  }

  return (
    <div style={{ maxWidth: 1200, margin: '0 auto', padding: 24, display: 'flex', flexDirection: 'column', gap: 16 }}>
      <h2 style={{ fontSize: 18, color: '#ccc', margin: 0 }}>Model Evaluation</h2>

      {error && (
        <div style={{ padding: 12, background: '#3a1a1a', border: '1px solid #5a2a2a', borderRadius: 6, color: '#f87171', fontSize: 13 }}>
          {error}
        </div>
      )}

      {/* Trigger form */}
      <div style={{ background: '#1a1a2e', borderRadius: 8, padding: 16, border: '1px solid #2a2a3e' }}>
        <h3 style={{ margin: '0 0 12px', fontSize: 14, color: '#ccc' }}>Run Evaluation</h3>
        <div style={{ display: 'flex', gap: 12, alignItems: 'flex-end', flexWrap: 'wrap' }}>
          <div>
            <label style={{ fontSize: 11, color: '#888', display: 'block', marginBottom: 2 }}>Model</label>
            <select
              value={selectedModel}
              onChange={e => setSelectedModel(e.target.value)}
              style={{ ...fieldStyle, minWidth: 200 }}
              disabled={running}
            >
              {models.length === 0 && <option value="">No models available</option>}
              {models.map(m => (
                <option key={m.path} value={m.path}>
                  {m.path.split('/').pop()} (step {m.step})
                </option>
              ))}
            </select>
          </div>
          <div>
            <label style={{ fontSize: 11, color: '#888', display: 'block', marginBottom: 2 }}>Bot Level</label>
            <select
              value={botLevel}
              onChange={e => setBotLevel(Number(e.target.value))}
              style={fieldStyle}
              disabled={running}
            >
              {[1, 2, 3, 4, 5].map(l => (
                <option key={l} value={l}>Level {l}</option>
              ))}
            </select>
          </div>
          <div>
            <label style={{ fontSize: 11, color: '#888', display: 'block', marginBottom: 2 }}>Games</label>
            <input
              type="number"
              value={nGames}
              onChange={e => setNGames(Number(e.target.value))}
              min={1}
              max={500}
              style={{ ...fieldStyle, width: 80 }}
              disabled={running}
            />
          </div>
          <button
            onClick={handleRun}
            disabled={running || !selectedModel}
            style={{
              ...btnStyle,
              background: running || !selectedModel ? '#2a2a3e' : '#3b82f6',
              color: running || !selectedModel ? '#666' : '#fff',
              cursor: running || !selectedModel ? 'not-allowed' : 'pointer',
            }}
          >
            {running ? 'Running...' : 'Run Evaluation'}
          </button>
        </div>
      </div>

      {/* Filter + Chart */}
      <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
        <span style={{ fontSize: 12, color: '#888' }}>Filter by level:</span>
        <button
          onClick={() => setFilterLevel(null)}
          style={{ ...btnStyle, padding: '4px 10px', fontSize: 11, background: filterLevel === null ? '#3b82f6' : '#2a2a3e', color: filterLevel === null ? '#fff' : '#888' }}
        >
          All
        </button>
        {[1, 2, 3, 4, 5].map(l => (
          <button
            key={l}
            onClick={() => setFilterLevel(l)}
            style={{ ...btnStyle, padding: '4px 10px', fontSize: 11, background: filterLevel === l ? '#3b82f6' : '#2a2a3e', color: filterLevel === l ? '#fff' : '#888' }}
          >
            L{l}
          </button>
        ))}
      </div>

      <EvalChart results={results} filterLevel={filterLevel} />

      {/* Results table */}
      <div style={{ background: '#1a1a2e', borderRadius: 8, border: '1px solid #2a2a3e', overflow: 'hidden' }}>
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
          <thead>
            <tr style={{ borderBottom: '1px solid #2a2a3e' }}>
              {['Model', 'Bot Level', 'Games', 'Win Rate', 'Avg Score', 'Avg Rally'].map(h => (
                <th key={h} style={{ textAlign: 'left', padding: '10px 14px', color: '#888', fontWeight: 500 }}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {results.length === 0 ? (
              <tr>
                <td colSpan={6} style={{ padding: 24, textAlign: 'center', color: '#666' }}>No evaluation results yet.</td>
              </tr>
            ) : (
              results.map((r, i) => (
                <tr key={i} style={{ borderBottom: '1px solid #1f1f30' }}>
                  <td style={{ padding: '8px 14px', color: '#ccc' }}>{r.modelPath.split('/').pop()}</td>
                  <td style={{ padding: '8px 14px' }}>L{r.botLevel}</td>
                  <td style={{ padding: '8px 14px', color: '#888' }}>{r.nGames}</td>
                  <td style={{ padding: '8px 14px', color: '#22c55e', fontWeight: 600 }}>
                    {(r.winRate * 100).toFixed(1)}%
                  </td>
                  <td style={{ padding: '8px 14px', color: '#888' }}>{r.avgScore.toFixed(1)}</td>
                  <td style={{ padding: '8px 14px', color: '#888' }}>{r.avgRallyLength.toFixed(1)}</td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  )
}
