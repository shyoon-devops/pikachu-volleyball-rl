import { useState, useEffect, useRef, useCallback } from 'react'
import {
  getModels,
  getEvalResults,
  runEvaluation,
  getEvaluationStatus,
} from '../../lib/api'
import { EvalChart } from './EvalChart'
import { CheckpointList } from './CheckpointList'
import type { ModelInfo, EvalResult } from '../../lib/types'
import './EvalPanel.css'

/**
 * Poll cadence for `GET /api/evaluation/status/{job_id}`. 2s matches
 * PM's spec and is comfortable for an evaluation that runs for
 * minutes to tens of minutes — tight enough that the progress badge
 * feels live, loose enough that the BE request rate is negligible
 * compared to the actual evaluation cost.
 */
const EVAL_POLL_INTERVAL_MS = 2000

/**
 * sessionStorage key for the active evaluation job id (FC-R3 user
 * report, 2026-04-18). The panel state itself is unmounted on tab
 * navigation — without persistence the job_id leaks and the Run
 * button lights back up, which users promptly re-click → 409
 * "Evaluation already in progress".
 *
 * sessionStorage (not localStorage) is the right scope: the job
 * lives on the single BE process, so re-opening the tab later after
 * a server restart should not resume a dead id. Cleared on any
 * terminal state (done/failed) and on 404 (job evicted).
 *
 * [BE-WAITING] Once BE adds `GET /api/evaluation/active` (returns
 * the current running job_id or 404), we can drop the sessionStorage
 * shim in favour of a fetch on mount. Until then, this is FE-only
 * and adequate for in-tab route changes.
 */
const ACTIVE_EVAL_JOB_KEY = 'eval:active_job_id'

function readStoredJobId(): string | null {
  try {
    return sessionStorage.getItem(ACTIVE_EVAL_JOB_KEY)
  } catch {
    // Private-mode Safari throws on sessionStorage access.
    return null
  }
}

function writeStoredJobId(jobId: string | null): void {
  try {
    if (jobId === null) sessionStorage.removeItem(ACTIVE_EVAL_JOB_KEY)
    else sessionStorage.setItem(ACTIVE_EVAL_JOB_KEY, jobId)
  } catch {
    // As above — swallow storage failures; the runtime fallback is
    // "no persistence" which is still better than crashing.
  }
}

type JobUiState =
  | { kind: 'idle' }
  | { kind: 'running'; jobId: string; current: number; total: number }
  | { kind: 'busy-already'; message: string }

export function EvalPanel() {
  const [models, setModels] = useState<ModelInfo[]>([])
  const [results, setResults] = useState<EvalResult[]>([])
  const [selectedModel, setSelectedModel] = useState('')
  const [botLevel, setBotLevel] = useState(1)
  const [nGames, setNGames] = useState(50)
  const [filterLevel, setFilterLevel] = useState<number | null>(null)
  const [loading, setLoading] = useState(true)
  const [job, setJob] = useState<JobUiState>({ kind: 'idle' })
  const [error, setError] = useState<string | null>(null)

  /**
   * Latest job id the UI is tracking. Kept in a ref (not just state)
   * so the polling timer callback sees the up-to-date value without
   * re-registering the setInterval on every render.
   */
  const jobIdRef = useRef<string | null>(null)
  const pollTimerRef = useRef<ReturnType<typeof setInterval> | null>(null)

  const stopPolling = useCallback(() => {
    if (pollTimerRef.current) {
      clearInterval(pollTimerRef.current)
      pollTimerRef.current = null
    }
  }, [])

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

  // Stop the poller on unmount so a navigation away mid-evaluation
  // doesn't leave the timer running forever.
  useEffect(() => stopPolling, [stopPolling])

  /**
   * Poll tick — called every EVAL_POLL_INTERVAL_MS. Reads the current
   * `jobIdRef.current` so switching jobs mid-poll picks up the new id
   * on the very next tick instead of the next setInterval cycle.
   */
  const pollOnce = useCallback(async () => {
    const id = jobIdRef.current
    if (!id) return
    try {
      const s = await getEvaluationStatus(id)
      if (s.state === 'pending' || s.state === 'running') {
        setJob({
          kind: 'running',
          jobId: id,
          current: s.progress.current,
          total: s.progress.total,
        })
        return
      }
      if (s.state === 'done') {
        stopPolling()
        jobIdRef.current = null
        writeStoredJobId(null)
        setJob({ kind: 'idle' })
        // Re-pull the results list so the new row lands in the table
        // even if the BE doesn't push it via another channel.
        const fresh = await getEvalResults()
        setResults(fresh)
        return
      }
      if (s.state === 'failed') {
        stopPolling()
        jobIdRef.current = null
        writeStoredJobId(null)
        setJob({ kind: 'idle' })
        setError(s.error ?? 'Evaluation failed')
      }
    } catch (err) {
      // 404 means the job was evicted (BE restart or expired registry);
      // stop polling and surface it as an error so the user can retry.
      const msg = err instanceof Error ? err.message : String(err)
      if (msg.includes('404') || msg.includes('not found')) {
        stopPolling()
        jobIdRef.current = null
        writeStoredJobId(null)
        setJob({ kind: 'idle' })
        setError('Evaluation job not found — it may have been evicted. Try again.')
      }
      // Any other transient error (network blip, 5xx) is silent — the
      // next tick retries. 2s cadence is forgiving enough to recover
      // without the user seeing a flash of error.
    }
  }, [stopPolling])

  const startPolling = useCallback(
    (jobId: string) => {
      jobIdRef.current = jobId
      stopPolling()
      // Fire once immediately so the progress label updates without
      // waiting the full interval on job start.
      void pollOnce()
      pollTimerRef.current = setInterval(() => {
        void pollOnce()
      }, EVAL_POLL_INTERVAL_MS)
    },
    [pollOnce, stopPolling],
  )

  /**
   * Resume polling on mount if a prior evaluation was still in flight
   * when the user navigated away (FC-R3, 2026-04-18). We write the
   * job_id to sessionStorage on POST and clear it on any terminal
   * transition, so the presence of a stored id here means "the last
   * job is still pending/running as far as the FE knows" — we call
   * /status once to confirm:
   *   pending/running → restore UI to running + resume polling
   *   done/failed     → clean terminal transitions (clears storage,
   *                     refetches results if done)
   *   404             → storage was stale (BE restart / TTL eviction);
   *                     silently drop the id and start fresh
   *
   * Intentionally runs ONCE on mount. Re-subscribing on every id
   * change would race the Run handler's own startPolling call.
   */
  useEffect(() => {
    const storedId = readStoredJobId()
    if (!storedId) return
    jobIdRef.current = storedId
    setJob({
      kind: 'running',
      jobId: storedId,
      current: 0,
      total: 0,
    })
    startPolling(storedId)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const handleRun = useCallback(async () => {
    if (!selectedModel) return
    if (job.kind !== 'idle') return
    setError(null)
    try {
      const ack = await runEvaluation(selectedModel, botLevel, nGames)
      writeStoredJobId(ack.jobId)
      setJob({
        kind: 'running',
        jobId: ack.jobId,
        current: 0,
        total: nGames,
      })
      startPolling(ack.jobId)
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Evaluation failed'
      // BE still returns 409 when another evaluation is already in
      // progress (routes.py:725-727). Surface a user-friendly message
      // rather than the raw error; leave the button disabled so the
      // user can't spam-click while the other job runs to completion.
      if (msg.includes('409') || msg.toLowerCase().includes('already in progress')) {
        setJob({
          kind: 'busy-already',
          message: 'Another evaluation is already in progress — wait for it to finish.',
        })
        return
      }
      setError(msg)
    }
  }, [selectedModel, botLevel, nGames, job.kind, startPolling])

  const isRunning = job.kind === 'running' || job.kind === 'busy-already'
  const progressLabel =
    job.kind === 'running'
      ? `Running ${job.current}/${job.total}`
      : job.kind === 'busy-already'
        ? 'Waiting for current run...'
        : 'Run Evaluation'

  if (loading) {
    return <div className="eval-panel-loading"><div className="spinner" />Loading...</div>
  }

  return (
    <div className="eval-panel">
      <h2 className="eval-panel-title">Model Evaluation</h2>

      {error && (
        <div className="eval-panel-error alert-error">{error}</div>
      )}

      {job.kind === 'busy-already' && (
        <div className="eval-panel-error alert-error" role="status" aria-live="polite">
          {job.message}
        </div>
      )}

      <div className="eval-form card">
        <h3 className="eval-form-title">Run Evaluation</h3>
        <div className="eval-form-field">
          <label className="eval-form-label" id="eval-checkpoint-label">Model Checkpoint</label>
          <CheckpointList
            models={models}
            selectedPath={selectedModel}
            onSelect={setSelectedModel}
            disabled={isRunning}
          />
        </div>
        <div className="eval-form-row">
          <div>
            <label className="eval-form-label">Bot Level</label>
            <select
              value={botLevel}
              onChange={e => setBotLevel(Number(e.target.value))}
              className="eval-form-select"
              disabled={isRunning}
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
              disabled={isRunning}
            />
          </div>
          <button
            onClick={handleRun}
            disabled={isRunning || !selectedModel}
            className="eval-form-submit btn btn-primary"
            aria-live="polite"
          >
            {progressLabel}
          </button>
        </div>
        {job.kind === 'running' && job.total > 0 && (
          <progress
            className="eval-form-progress"
            max={job.total}
            value={job.current}
            aria-label={`Evaluation progress: ${job.current} of ${job.total} games`}
          />
        )}
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
