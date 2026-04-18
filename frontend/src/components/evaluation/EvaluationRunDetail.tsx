import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Link, useParams, useSearchParams } from 'react-router-dom'
import {
  getModels,
  runEvaluation,
  getEvaluationStatus,
} from '../../lib/api'
import { formatKstDateTime } from '../../lib/formatTime'
import { useTrainingState } from '../../hooks/useTrainingState'
import type { ModelInfo } from '../../lib/types'
import './EvaluationRunDetail.css'

/**
 * Level-2 drill-down for `/evaluation/:title` (FC-R7C, spec
 * `DESIGN-EVAL-DRILLDOWN.md`).
 *
 * Lists the checkpoints of a single training run (BE-T8 `/api/models
 * ?title=X`) and provides the "Run Evaluation" form wired to the
 * existing async eval job pipeline. Replaces the flat eval panel.
 *
 * Layout regions (per spec §2):
 *   2a. Run-info header — breadcrumb + h1 title + status chip
 *   2b. Checkpoint table — radio select / step / saved at / size /
 *       filename
 *   2c. Eval runner panel — bot_level select + n_games input +
 *       Run Evaluation primary button
 */

/** Poll cadence matches the legacy EvalPanel — 2s keeps the progress
 *  badge live without flooding the BE. */
const EVAL_POLL_INTERVAL_MS = 2000

/** sessionStorage scope — survives tab navigation in the same tab. */
const ACTIVE_EVAL_JOB_KEY = 'eval:active_job_id'

/** URL-persisted `bot_level` picker — FC-R6F pattern carried over. */
const BOT_LEVEL_QUERY_KEY = 'bot_level'

function parseBotLevelParam(raw: string | null): number {
  if (raw === null) return 1
  const n = Number(raw)
  if (!Number.isInteger(n) || n < 1 || n > 5) return 1
  return n
}

function readStoredJobId(): string | null {
  try { return sessionStorage.getItem(ACTIVE_EVAL_JOB_KEY) } catch { return null }
}

function writeStoredJobId(jobId: string | null): void {
  try {
    if (jobId === null) sessionStorage.removeItem(ACTIVE_EVAL_JOB_KEY)
    else sessionStorage.setItem(ACTIVE_EVAL_JOB_KEY, jobId)
  } catch { /* private-mode swallow */ }
}

type JobUiState =
  | { kind: 'idle' }
  | { kind: 'running'; jobId: string; current: number; total: number }
  | { kind: 'busy-already'; message: string }

function formatBytes(n: number): string {
  if (!Number.isFinite(n) || n <= 0) return '—'
  const mb = n / (1024 * 1024)
  if (mb >= 1) return `${mb.toFixed(1)} MB`
  const kb = n / 1024
  return `${kb.toFixed(0)} KB`
}

function formatStep(step: number | null | undefined): string {
  if (step === null || step === undefined) return '—'
  // BE sentinel for `__final` checkpoints — render as 'final' instead
  // of "1,000,000,000,000" which would blow the table layout.
  if (step >= 10 ** 12) return 'final'
  return step.toLocaleString()
}

export function EvaluationRunDetail() {
  const { title = '' } = useParams<{ title: string }>()
  const decoded = decodeURIComponent(title)
  const [searchParams, setSearchParams] = useSearchParams()
  const { status } = useTrainingState()

  // Treat this title as "active" only when the live training manager
  // reports it running — checkpoint mutations (R7D) gate on this.
  const isActiveRun =
    status.state === 'running' && (status.title ?? '').trim() === decoded.trim()

  const botLevel = parseBotLevelParam(searchParams.get(BOT_LEVEL_QUERY_KEY))
  const setBotLevel = useCallback(
    (next: number) => {
      const params = new URLSearchParams(searchParams)
      if (next === 1) params.delete(BOT_LEVEL_QUERY_KEY)
      else params.set(BOT_LEVEL_QUERY_KEY, String(next))
      setSearchParams(params, { replace: true })
    },
    [searchParams, setSearchParams],
  )

  const [models, setModels] = useState<ModelInfo[]>([])
  const [selectedPath, setSelectedPath] = useState<string>('')
  const [nGames, setNGames] = useState(20)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [job, setJob] = useState<JobUiState>({ kind: 'idle' })

  const jobIdRef = useRef<string | null>(null)
  const pollTimerRef = useRef<ReturnType<typeof setInterval> | null>(null)

  // Refetch models on every game:result as well — training-in-flight
  // writes new checkpoints periodically so the list should reflect
  // them without a manual refresh.
  const fetchModels = useCallback(async () => {
    try {
      const rows = await getModels(decoded)
      setModels(rows)
      setError(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load checkpoints')
    }
  }, [decoded])

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    fetchModels().finally(() => {
      if (!cancelled) setLoading(false)
    })
    return () => { cancelled = true }
  }, [fetchModels])

  const stopPolling = useCallback(() => {
    if (pollTimerRef.current) {
      clearInterval(pollTimerRef.current)
      pollTimerRef.current = null
    }
  }, [])

  useEffect(() => stopPolling, [stopPolling])

  const pollOnce = useCallback(async () => {
    const id = jobIdRef.current
    if (!id) return
    try {
      const s = await getEvaluationStatus(id)
      if (s.state === 'pending' || s.state === 'running') {
        setJob({ kind: 'running', jobId: id, current: s.progress.current, total: s.progress.total })
        return
      }
      if (s.state === 'done') {
        stopPolling()
        jobIdRef.current = null
        writeStoredJobId(null)
        setJob({ kind: 'idle' })
        // No post-run results table on this page — the toast-equivalent
        // is just the button clearing. A follow-up may add an inline
        // result chip; omitted to keep R7C scope tight.
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
      const msg = err instanceof Error ? err.message : String(err)
      if (msg.includes('404') || msg.includes('not found')) {
        stopPolling()
        jobIdRef.current = null
        writeStoredJobId(null)
        setJob({ kind: 'idle' })
        setError('Evaluation job not found — it may have been evicted. Try again.')
      }
      // Transient errors are silent — next tick retries.
    }
  }, [stopPolling])

  const startPolling = useCallback(
    (jobId: string) => {
      jobIdRef.current = jobId
      stopPolling()
      void pollOnce()
      pollTimerRef.current = setInterval(() => { void pollOnce() }, EVAL_POLL_INTERVAL_MS)
    },
    [pollOnce, stopPolling],
  )

  useEffect(() => {
    const storedId = readStoredJobId()
    if (!storedId) return
    jobIdRef.current = storedId
    setJob({ kind: 'running', jobId: storedId, current: 0, total: 0 })
    startPolling(storedId)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const handleRun = useCallback(async () => {
    if (!selectedPath) return
    if (job.kind !== 'idle') return
    setError(null)
    try {
      const ack = await runEvaluation(selectedPath, botLevel, nGames)
      writeStoredJobId(ack.jobId)
      setJob({ kind: 'running', jobId: ack.jobId, current: 0, total: nGames })
      startPolling(ack.jobId)
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Evaluation failed'
      if (msg.includes('409') || msg.toLowerCase().includes('already in progress')) {
        setJob({
          kind: 'busy-already',
          message: 'Another evaluation is already in progress — wait for it to finish.',
        })
        return
      }
      setError(msg)
    }
  }, [selectedPath, botLevel, nGames, job.kind, startPolling])

  const isRunning = job.kind === 'running' || job.kind === 'busy-already'
  const selectedStepLabel = useMemo(() => {
    const row = models.find(m => m.path === selectedPath)
    if (!row) return '체크포인트를 선택하세요'
    return `선택됨: step ${formatStep(row.step)}`
  }, [models, selectedPath])

  return (
    <div className="eval-run-detail">
      <nav className="eval-run-detail-breadcrumb" aria-label="Breadcrumb">
        <Link to="/evaluation" className="eval-run-detail-breadcrumb-link">
          All Trainings
        </Link>
        <span className="eval-run-detail-breadcrumb-separator" aria-hidden="true">
          {' › '}
        </span>
        <span className="eval-run-detail-breadcrumb-current">
          {decoded || 'untitled'}
        </span>
      </nav>
      <div className="eval-run-detail-header">
        <h1 className="eval-run-detail-title">{decoded || 'untitled'}</h1>
        {isActiveRun && (
          <span className="eval-run-detail-live" aria-label="This training run is currently running">
            Running
          </span>
        )}
      </div>

      {error && (
        <div className="eval-run-detail-error alert-error" role="alert">{error}</div>
      )}

      {job.kind === 'busy-already' && (
        <div className="eval-run-detail-error alert-error" role="status" aria-live="polite">
          {job.message}
        </div>
      )}

      <div className="eval-run-detail-table-wrapper card table-scroll">
        <table className="eval-run-detail-table" aria-label="Checkpoints">
          <thead>
            <tr>
              <th scope="col" className="eval-run-detail-col-radio">
                <span className="sr-only">Select</span>
              </th>
              <th scope="col">Step</th>
              <th scope="col">Saved at</th>
              <th scope="col">Size</th>
              <th scope="col">Filename</th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr>
                <td colSpan={5} className="eval-run-detail-empty">Loading…</td>
              </tr>
            ) : models.length === 0 ? (
              <tr>
                <td colSpan={5} className="eval-run-detail-empty empty-state">
                  {isActiveRun
                    ? '이 학습의 체크포인트가 아직 없습니다. 학습이 진행되면 자동 저장됩니다.'
                    : '이 학습의 체크포인트가 없습니다.'}
                </td>
              </tr>
            ) : (
              models.map(m => {
                const selected = m.path === selectedPath
                return (
                  <tr
                    key={m.path}
                    className={`eval-run-detail-row${selected ? ' eval-run-detail-row--selected' : ''}`}
                    onClick={() => setSelectedPath(m.path)}
                  >
                    <td className="eval-run-detail-col-radio">
                      <input
                        type="radio"
                        name="eval-checkpoint"
                        value={m.path}
                        checked={selected}
                        onChange={() => setSelectedPath(m.path)}
                        aria-label={`Select checkpoint step ${formatStep(m.step)}`}
                      />
                    </td>
                    <td className="eval-run-detail-cell-step">{formatStep(m.step)}</td>
                    <td className="text-muted">
                      {m.createdAt ? formatKstDateTime(m.createdAt) : '—'}
                    </td>
                    <td className="text-muted">{formatBytes(m.sizeBytes)}</td>
                    <td
                      className="text-muted text-mono eval-run-detail-cell-filename"
                      title={m.filename ?? m.path}
                    >
                      {m.filename ?? m.path}
                    </td>
                  </tr>
                )
              })
            )}
          </tbody>
        </table>
      </div>

      <div className="eval-run-detail-runner card">
        <div className="eval-run-detail-runner-label">{selectedStepLabel}</div>
        <div className="eval-run-detail-runner-row">
          <label className="eval-run-detail-field">
            <span className="eval-run-detail-field-label">Bot Level</span>
            <select
              value={botLevel}
              onChange={e => setBotLevel(Number(e.target.value))}
              className="eval-run-detail-select"
              disabled={isRunning}
            >
              {[1, 2, 3, 4, 5].map(l => (
                <option key={l} value={l}>Level {l}</option>
              ))}
            </select>
          </label>
          <label className="eval-run-detail-field">
            <span className="eval-run-detail-field-label">Games</span>
            <input
              type="number"
              value={nGames}
              onChange={e => setNGames(Number(e.target.value))}
              min={1}
              max={200}
              className="eval-run-detail-input"
              disabled={isRunning}
            />
          </label>
          <button
            type="button"
            onClick={handleRun}
            disabled={isRunning || !selectedPath}
            className="eval-run-detail-submit btn btn-primary"
            aria-live="polite"
          >
            {job.kind === 'running'
              ? `Running ${job.current}/${job.total}`
              : job.kind === 'busy-already'
                ? 'Waiting…'
                : '평가 실행'}
          </button>
        </div>
        {job.kind === 'running' && job.total > 0 && (
          <progress
            className="eval-run-detail-progress"
            max={job.total}
            value={job.current}
            aria-label={`Evaluation progress: ${job.current} of ${job.total} games`}
          />
        )}
      </div>
    </div>
  )
}
