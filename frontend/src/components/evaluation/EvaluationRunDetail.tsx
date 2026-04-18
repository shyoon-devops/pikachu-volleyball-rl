import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Link, useParams, useSearchParams } from 'react-router-dom'
import {
  getModels,
  deleteModels,
  runEvaluation,
  getEvaluationStatus,
} from '../../lib/api'
import { formatKstDateTime } from '../../lib/formatTime'
import { useTrainingState } from '../../hooks/useTrainingState'
import type { ModelInfo } from '../../lib/types'
import { DeleteCheckpointsModal } from './DeleteCheckpointsModal'
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

  /**
   * FC-R7D delete-mode state. Spec `DESIGN-BULK-DELETE.md §1`
   * recommends Option A (explicit mode toggle) over always-on
   * checkboxes, so we keep Delete Mode as its own flag rather than
   * inferring from the selection set.
   *
   * `selectedForDelete` is a Set<path> because toggle/shift/clear
   * semantics read more cleanly as add/remove on a Set than filter
   * on an array; at render time we just ask `has(path)`.
   */
  const [deleteMode, setDeleteMode] = useState(false)
  const [selectedForDelete, setSelectedForDelete] = useState<Set<string>>(new Set())
  const [confirmOpen, setConfirmOpen] = useState(false)
  const [deleteInflight, setDeleteInflight] = useState(false)
  const [deleteError, setDeleteError] = useState<string | null>(null)
  const [deleteToast, setDeleteToast] = useState<string | null>(null)

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

  // Highest-step checkpoint surfaced for the modal's latest-warning
  // body. `10**12` is the BE sentinel for `__final` and sorts above
  // every real step, so this also picks up "final" when present.
  const latestStep = useMemo(() => {
    let hi: number | null = null
    for (const m of models) {
      const s = typeof m.step === 'number' ? m.step : null
      if (s === null) continue
      if (hi === null || s > hi) hi = s
    }
    return hi
  }, [models])

  const selectedModelRows = useMemo(
    () => models.filter(m => selectedForDelete.has(m.path)),
    [models, selectedForDelete],
  )

  const includingLatest = useMemo(() => {
    if (latestStep === null) return false
    return selectedModelRows.some(
      m => typeof m.step === 'number' && m.step === latestStep,
    )
  }, [selectedModelRows, latestStep])

  const enterDeleteMode = useCallback(() => {
    setDeleteMode(true)
    setDeleteError(null)
    setDeleteToast(null)
  }, [])

  const exitDeleteMode = useCallback(() => {
    setDeleteMode(false)
    setSelectedForDelete(new Set())
    setConfirmOpen(false)
    setDeleteError(null)
  }, [])

  const toggleSelected = useCallback((path: string) => {
    setSelectedForDelete(prev => {
      const next = new Set(prev)
      if (next.has(path)) next.delete(path)
      else next.add(path)
      return next
    })
  }, [])

  const selectAll = useCallback(() => {
    setSelectedForDelete(new Set(models.map(m => m.path)))
  }, [models])

  const clearSelection = useCallback(() => {
    setSelectedForDelete(new Set())
  }, [])

  /**
   * Header tri-state: unchecked (0 selected), checked (all selected),
   * or indeterminate (mixed). We set the DOM property via a ref
   * callback because the `indeterminate` boolean isn't a JSX prop.
   */
  const headerCheckboxRef = useCallback(
    (el: HTMLInputElement | null) => {
      if (!el) return
      const n = selectedForDelete.size
      const total = models.length
      el.indeterminate = n > 0 && n < total
    },
    [selectedForDelete, models.length],
  )

  const runDelete = useCallback(async () => {
    if (selectedForDelete.size === 0) return
    setDeleteInflight(true)
    setDeleteError(null)
    const paths = Array.from(selectedForDelete)
    const prevModels = models
    // Optimistic removal — UI updates immediately, rollback on failure.
    setModels(rows => rows.filter(r => !selectedForDelete.has(r.path)))
    try {
      const res = await deleteModels(paths)
      setConfirmOpen(false)
      // BE reports per-path failures separately from HTTP success.
      // Restore any failed rows so the user can see + retry — the
      // optimistic removal already hid them.
      if (res.failed.length > 0) {
        const failedPaths = new Set(res.failed.map(f => f.path))
        const restored = prevModels.filter(r => failedPaths.has(r.path))
        setModels(curr => {
          const byPath = new Map(curr.map(r => [r.path, r] as const))
          for (const r of restored) byPath.set(r.path, r)
          return [...byPath.values()]
        })
        setDeleteError(
          `일부 파일 삭제 실패 (${res.failed.length}개): ${res.failed[0].reason}`,
        )
      } else {
        setDeleteToast(`${res.deleted.length}개 삭제 완료`)
      }
      setSelectedForDelete(new Set())
      setDeleteMode(false)
    } catch (err) {
      // Rollback on outright failure (409 active-run, 5xx, network blip).
      setModels(prevModels)
      const msg = err instanceof Error ? err.message : 'Failed to delete checkpoints'
      if (msg.includes('409')) {
        setDeleteError('진행 중인 학습의 체크포인트는 삭제할 수 없습니다. 학습 종료 후 다시 시도하세요.')
      } else {
        setDeleteError(msg)
      }
    } finally {
      setDeleteInflight(false)
    }
  }, [selectedForDelete, models])

  // Auto-dismiss the success toast after 5s (spec §6).
  useEffect(() => {
    if (!deleteToast) return
    const id = setTimeout(() => setDeleteToast(null), 5000)
    return () => clearTimeout(id)
  }, [deleteToast])

  const activeRunTooltip =
    '진행 중인 학습의 체크포인트는 삭제할 수 없습니다. 학습 종료 후 다시 시도하세요.'

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

      {/*
        Delete-mode toolbar (FC-R7D, spec §2). Lives above the table.
        The "선택 삭제" entry button is disabled + tooltipped when the
        live training matches this title; `title` attr keeps the
        tooltip reachable without a custom popover layer.
      */}
      <div className="eval-run-detail-delete-toolbar" role="toolbar" aria-label="Bulk delete controls">
        {!deleteMode ? (
          <button
            type="button"
            onClick={enterDeleteMode}
            disabled={isActiveRun || models.length === 0}
            title={isActiveRun ? activeRunTooltip : undefined}
            className="eval-run-detail-delete-enter btn btn-ghost"
          >
            선택 삭제
          </button>
        ) : (
          <>
            <span className="eval-run-detail-delete-count">
              {`선택됨: ${selectedForDelete.size} / ${models.length}`}
            </span>
            <button
              type="button"
              onClick={selectAll}
              className="eval-run-detail-delete-link"
            >
              모두 선택
            </button>
            <button
              type="button"
              onClick={clearSelection}
              className="eval-run-detail-delete-link"
            >
              모두 해제
            </button>
            <div className="eval-run-detail-delete-spacer" />
            <button
              type="button"
              onClick={() => setConfirmOpen(true)}
              disabled={selectedForDelete.size === 0 || isActiveRun}
              title={isActiveRun ? activeRunTooltip : undefined}
              className="eval-run-detail-delete-commit btn btn-danger"
            >
              {`선택한 ${selectedForDelete.size}개 삭제`}
            </button>
            <button
              type="button"
              onClick={exitDeleteMode}
              className="eval-run-detail-delete-cancel btn btn-ghost"
            >
              취소
            </button>
          </>
        )}
        {deleteError && !confirmOpen && (
          <div className="eval-run-detail-error alert-error" role="alert">
            {deleteError}
          </div>
        )}
      </div>

      {deleteToast && (
        <div className="eval-run-detail-toast" role="status" aria-live="polite">
          {deleteToast}
        </div>
      )}

      <div className="eval-run-detail-table-wrapper card table-scroll">
        <table className="eval-run-detail-table" aria-label="Checkpoints">
          <thead>
            <tr>
              {deleteMode && (
                <th scope="col" className="eval-run-detail-col-check">
                  <input
                    type="checkbox"
                    ref={headerCheckboxRef}
                    checked={models.length > 0 && selectedForDelete.size === models.length}
                    onChange={() => {
                      if (selectedForDelete.size === models.length) clearSelection()
                      else selectAll()
                    }}
                    disabled={isActiveRun}
                    aria-label="Select all checkpoints"
                    title={isActiveRun ? activeRunTooltip : undefined}
                  />
                </th>
              )}
              <th
                scope="col"
                className={`eval-run-detail-col-radio${deleteMode ? ' eval-run-detail-col-radio--dim' : ''}`}
              >
                <span className="sr-only">Select for eval</span>
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
                <td colSpan={deleteMode ? 6 : 5} className="eval-run-detail-empty">Loading…</td>
              </tr>
            ) : models.length === 0 ? (
              <tr>
                <td colSpan={deleteMode ? 6 : 5} className="eval-run-detail-empty empty-state">
                  {isActiveRun
                    ? '이 학습의 체크포인트가 아직 없습니다. 학습이 진행되면 자동 저장됩니다.'
                    : '이 학습의 체크포인트가 없습니다.'}
                </td>
              </tr>
            ) : (
              models.map(m => {
                const selected = m.path === selectedPath
                const checked = selectedForDelete.has(m.path)
                return (
                  <tr
                    key={m.path}
                    className={`eval-run-detail-row${selected && !deleteMode ? ' eval-run-detail-row--selected' : ''}${checked ? ' eval-run-detail-row--delete-checked' : ''}`}
                    onClick={() => {
                      if (deleteMode) {
                        if (isActiveRun) return
                        toggleSelected(m.path)
                      } else {
                        setSelectedPath(m.path)
                      }
                    }}
                  >
                    {deleteMode && (
                      <td
                        className="eval-run-detail-col-check"
                        onClick={e => e.stopPropagation()}
                      >
                        <input
                          type="checkbox"
                          checked={checked}
                          disabled={isActiveRun}
                          title={isActiveRun ? activeRunTooltip : undefined}
                          onChange={() => toggleSelected(m.path)}
                          aria-label={`Select checkpoint step ${formatStep(m.step)} for delete`}
                        />
                      </td>
                    )}
                    <td
                      className={`eval-run-detail-col-radio${deleteMode ? ' eval-run-detail-col-radio--dim' : ''}`}
                      onClick={deleteMode ? e => e.stopPropagation() : undefined}
                    >
                      <input
                        type="radio"
                        name="eval-checkpoint"
                        value={m.path}
                        checked={selected}
                        onChange={() => setSelectedPath(m.path)}
                        disabled={deleteMode}
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

      <DeleteCheckpointsModal
        open={confirmOpen}
        selection={selectedModelRows}
        includingLatest={includingLatest}
        inflight={deleteInflight}
        errorMessage={deleteError}
        onCancel={() => {
          if (deleteInflight) return
          setConfirmOpen(false)
        }}
        onConfirm={runDelete}
      />
    </div>
  )
}
