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
    return (
      <div className="eval-panel__loading">
        <div className="spinner" />
        <span>Loading evaluation data...</span>
      </div>
    )
  }

  return (
    <div className="eval-panel">
      <h2 className="eval-panel__title">Model Evaluation</h2>

      {error && <div className="eval-panel__error">{error}</div>}

      <div className="eval-panel__form">
        <h3>Run Evaluation</h3>
        <div className="eval-panel__form-fields">
          <div className="eval-panel__field">
            <label>Model</label>
            <select
              value={selectedModel}
              onChange={e => setSelectedModel(e.target.value)}
              style={{ minWidth: 200 }}
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
          <div className="eval-panel__field">
            <label>Bot Level</label>
            <select
              value={botLevel}
              onChange={e => setBotLevel(Number(e.target.value))}
              disabled={running}
            >
              {[1, 2, 3, 4, 5].map(l => (
                <option key={l} value={l}>Level {l}</option>
              ))}
            </select>
          </div>
          <div className="eval-panel__field">
            <label>Games</label>
            <input
              type="number"
              value={nGames}
              onChange={e => setNGames(Number(e.target.value))}
              min={1}
              max={500}
              style={{ width: 80 }}
              disabled={running}
            />
          </div>
          <button
            onClick={handleRun}
            disabled={running || !selectedModel}
            className="btn btn-primary"
          >
            {running ? 'Running...' : 'Run Evaluation'}
          </button>
        </div>
      </div>

      <div className="eval-panel__filter">
        <span className="eval-panel__filter-label">Filter by level:</span>
        <button
          onClick={() => setFilterLevel(null)}
          className={`btn btn-ghost ${filterLevel === null ? 'active' : ''}`}
        >
          All
        </button>
        {[1, 2, 3, 4, 5].map(l => (
          <button
            key={l}
            onClick={() => setFilterLevel(l)}
            className={`btn btn-ghost ${filterLevel === l ? 'active' : ''}`}
          >
            L{l}
          </button>
        ))}
      </div>

      <EvalChart results={results} filterLevel={filterLevel} />

      <div className="eval-panel__table">
        <table>
          <thead>
            <tr>
              <th>Model</th>
              <th>Bot Level</th>
              <th>Games</th>
              <th>Win Rate</th>
              <th>Avg Score</th>
              <th>Avg Rally</th>
            </tr>
          </thead>
          <tbody>
            {results.length === 0 ? (
              <tr>
                <td colSpan={6}>
                  <div className="empty-state">
                    <div className="empty-state-icon">&#128202;</div>
                    <span>No evaluation results yet. Run an evaluation to compare models.</span>
                  </div>
                </td>
              </tr>
            ) : (
              results.map((r, i) => (
                <tr key={i}>
                  <td className="model-name">{r.modelPath.split('/').pop()}</td>
                  <td>L{r.botLevel}</td>
                  <td className="muted">{r.nGames}</td>
                  <td className="win-rate">{(r.winRate * 100).toFixed(1)}%</td>
                  <td className="muted">{r.avgScore.toFixed(1)}</td>
                  <td className="muted">{r.avgRallyLength.toFixed(1)}</td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  )
}
