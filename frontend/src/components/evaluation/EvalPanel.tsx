import { useState, useEffect } from 'react'
import { getModels, getEvalResults, runEvaluation } from '../../lib/api'
import { EvalChart } from './EvalChart'
import type { ModelInfo, EvalResult } from '../../lib/types'
<<<<<<< HEAD
import './EvalPanel.css'
=======

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
>>>>>>> github/yoon/designer

export function EvalPanel() {
  const [models, setModels] = useState<ModelInfo[]>([])
  const [results, setResults] = useState<EvalResult[]>([])
  const [selectedModel, setSelectedModel] = useState('')
  const [botLevel, setBotLevel] = useState(1)
  const [nGames, setNGames] = useState(50)
  const [filterLevel, setFilterLevel] = useState<number | null>(null)
  const [loading, setLoading] = useState(true)
  const [running, setRunning] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    Promise.all([getModels(), getEvalResults()])
      .then(([m, r]) => {
        if (cancelled) return
        setModels(m)
        setResults(r)
        if (m.length > 0) setSelectedModel(m[0].path)
      })
      .catch(err => {
        if (cancelled) return
        setError(err instanceof Error ? err.message : 'Failed to load data')
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => { cancelled = true }
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
<<<<<<< HEAD
    return <div className="eval-panel-loading">Loading...</div>
  }

  return (
    <div className="eval-panel">
      <h2 className="eval-panel-title">Model Evaluation</h2>

      {error && (
        <div className="eval-panel-error alert-error">{error}</div>
      )}

      <div className="eval-form card">
        <h3 className="eval-form-title">Run Evaluation</h3>
        <div className="eval-form-row">
          <div>
            <label className="eval-form-label">Model</label>
            <select
              value={selectedModel}
              onChange={e => setSelectedModel(e.target.value)}
              className="eval-form-select eval-form-select--model"
=======
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
>>>>>>> github/yoon/designer
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
<<<<<<< HEAD
            <label className="eval-form-label">Bot Level</label>
            <select
              value={botLevel}
              onChange={e => setBotLevel(Number(e.target.value))}
              className="eval-form-select"
=======
            <label style={{ fontSize: 11, color: '#888', display: 'block', marginBottom: 2 }}>Bot Level</label>
            <select
              value={botLevel}
              onChange={e => setBotLevel(Number(e.target.value))}
              style={fieldStyle}
>>>>>>> github/yoon/designer
              disabled={running}
            >
              {[1, 2, 3, 4, 5].map(l => (
                <option key={l} value={l}>Level {l}</option>
              ))}
            </select>
          </div>
          <div>
<<<<<<< HEAD
            <label className="eval-form-label">Games</label>
=======
            <label style={{ fontSize: 11, color: '#888', display: 'block', marginBottom: 2 }}>Games</label>
>>>>>>> github/yoon/designer
            <input
              type="number"
              value={nGames}
              onChange={e => setNGames(Number(e.target.value))}
              min={1}
              max={500}
<<<<<<< HEAD
              className="eval-form-input"
=======
              style={{ ...fieldStyle, width: 80 }}
>>>>>>> github/yoon/designer
              disabled={running}
            />
          </div>
          <button
            onClick={handleRun}
            disabled={running || !selectedModel}
<<<<<<< HEAD
            className="eval-form-submit"
=======
            style={{
              ...btnStyle,
              background: running || !selectedModel ? '#2a2a3e' : '#3b82f6',
              color: running || !selectedModel ? '#666' : '#fff',
              cursor: running || !selectedModel ? 'not-allowed' : 'pointer',
            }}
>>>>>>> github/yoon/designer
          >
            {running ? 'Running...' : 'Run Evaluation'}
          </button>
        </div>
      </div>

<<<<<<< HEAD
      <div className="eval-filter">
        <span className="eval-filter-label">Filter by level:</span>
        <button
          onClick={() => setFilterLevel(null)}
          className="eval-filter-btn"
          data-active={filterLevel === null}
=======
      {/* Filter + Chart */}
      <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
        <span style={{ fontSize: 12, color: '#888' }}>Filter by level:</span>
        <button
          onClick={() => setFilterLevel(null)}
          style={{ ...btnStyle, padding: '4px 10px', fontSize: 11, background: filterLevel === null ? '#3b82f6' : '#2a2a3e', color: filterLevel === null ? '#fff' : '#888' }}
>>>>>>> github/yoon/designer
        >
          All
        </button>
        {[1, 2, 3, 4, 5].map(l => (
          <button
            key={l}
            onClick={() => setFilterLevel(l)}
<<<<<<< HEAD
            className="eval-filter-btn"
            data-active={filterLevel === l}
=======
            style={{ ...btnStyle, padding: '4px 10px', fontSize: 11, background: filterLevel === l ? '#3b82f6' : '#2a2a3e', color: filterLevel === l ? '#fff' : '#888' }}
>>>>>>> github/yoon/designer
          >
            L{l}
          </button>
        ))}
      </div>

      <EvalChart results={results} filterLevel={filterLevel} />

<<<<<<< HEAD
      <div className="eval-results-table-wrapper card">
        <table className="eval-results-table">
          <thead>
            <tr>
              {['Model', 'Bot Level', 'Games', 'Win Rate', 'Avg Score', 'Avg Rally'].map(h => (
                <th key={h}>{h}</th>
=======
      {/* Results table */}
      <div style={{ background: '#1a1a2e', borderRadius: 8, border: '1px solid #2a2a3e', overflow: 'hidden' }}>
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
          <thead>
            <tr style={{ borderBottom: '1px solid #2a2a3e' }}>
              {['Model', 'Bot Level', 'Games', 'Win Rate', 'Avg Score', 'Avg Rally'].map(h => (
                <th key={h} style={{ textAlign: 'left', padding: '10px 14px', color: '#888', fontWeight: 500 }}>{h}</th>
>>>>>>> github/yoon/designer
              ))}
            </tr>
          </thead>
          <tbody>
            {results.length === 0 ? (
              <tr>
<<<<<<< HEAD
                <td colSpan={6} className="eval-results-empty">No evaluation results yet.</td>
              </tr>
            ) : (
              results.map((r, i) => (
                <tr key={i}>
                  <td>{r.modelPath.split('/').pop()}</td>
                  <td>L{r.botLevel}</td>
                  <td className="text-muted">{r.nGames}</td>
                  <td className="eval-results-winrate">
                    {(r.winRate * 100).toFixed(1)}%
                  </td>
                  <td className="text-muted">{r.avgScore.toFixed(1)}</td>
                  <td className="text-muted">{r.avgRallyLength.toFixed(1)}</td>
=======
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
>>>>>>> github/yoon/designer
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  )
}
