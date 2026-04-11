import { useState, useEffect } from 'react'
import { getModels, getEvalResults, runEvaluation } from '../../lib/api'
import { EvalChart } from './EvalChart'
import type { ModelInfo, EvalResult } from '../../lib/types'
import './EvalPanel.css'

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
    return <div className="eval-panel-loading"><div className="spinner" />Loading...</div>
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
              disabled={running}
            >
              {models.length === 0 && <option value="">No models available</option>}
              {models.map(m => (
                <option key={m.path} value={m.path}>
                  {m.path.split('/').pop()}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="eval-form-label">Bot Level</label>
            <select
              value={botLevel}
              onChange={e => setBotLevel(Number(e.target.value))}
              className="eval-form-select"
              disabled={running}
            >
              {[1, 2, 3, 4, 5].map(l => (
                <option key={l} value={l}>Level {l}</option>
              ))}
            </select>
          </div>
          <div>
            <label className="eval-form-label">Games</label>
            <input
              type="number"
              value={nGames}
              onChange={e => setNGames(Number(e.target.value))}
              min={1}
              max={500}
              className="eval-form-input"
              disabled={running}
            />
          </div>
          <button
            onClick={handleRun}
            disabled={running || !selectedModel}
            className="eval-form-submit btn btn-primary"
          >
            {running ? 'Running...' : 'Run Evaluation'}
          </button>
        </div>
      </div>

      <div className="eval-filter">
        <span className="eval-filter-label">Filter by level:</span>
        <button
          onClick={() => setFilterLevel(null)}
          className={`eval-filter-btn btn ${filterLevel === null ? 'btn-ghost active' : 'btn-ghost'}`}
        >
          All
        </button>
        {[1, 2, 3, 4, 5].map(l => (
          <button
            key={l}
            onClick={() => setFilterLevel(l)}
            className={`eval-filter-btn btn ${filterLevel === l ? 'btn-ghost active' : 'btn-ghost'}`}
          >
            L{l}
          </button>
        ))}
      </div>

      <EvalChart results={results} filterLevel={filterLevel} />

      <div className="eval-results-table-wrapper card table-scroll">
        <table className="eval-results-table">
          <thead>
            <tr>
              {['Model', 'Bot Level', 'Games', 'Win Rate', 'Avg Score', 'Avg Rally'].map(h => (
                <th key={h}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {results.length === 0 ? (
              <tr>
                <td colSpan={6} className="eval-results-empty empty-state">No evaluation results yet.</td>
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
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  )
}
