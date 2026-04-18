import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { getTrainingRuns } from '../../lib/api'
import type { TrainingRun } from '../../lib/types'
import { formatKstDateTime } from '../../lib/formatTime'
import './TrainingRunList.css'

/**
 * Level-1 drill-down: one row per training run. Spec c460c55b §1.
 *
 * BE (`GET /api/training/runs`, T4 fc38f3d8) returns aggregates
 * keyed on `title`, sorted desc by `started_at`, with an overlayed
 * `"running"` status when the live training manager is currently
 * pushing results under that title.
 *
 * Clicking a row navigates to `/history/{title}` — the level-2
 * page reuses the existing unified game list filtered by title.
 *
 * Search: a debounced 200ms filter applied CLIENT-SIDE against the
 * fetched page. BE doesn't expose a `q=` param on `/training/runs`
 * today; when it does, this component should re-query instead.
 * Until then, the 100-run BE cap is well above realistic training
 * counts so client-filtering is fine.
 */

const SEARCH_DEBOUNCE_MS = 200
const SEARCH_QUERY_KEY = 'q'
const PAGE_LIMIT = 50

export function TrainingRunList() {
  const [searchParams, setSearchParams] = useSearchParams()
  const [runs, setRuns] = useState<TrainingRun[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  /**
   * URL-backed search query (`?q=...`) so deep links + back-nav
   * preserve the user's filter state.
   */
  const urlQuery = searchParams.get(SEARCH_QUERY_KEY) ?? ''
  const [searchInput, setSearchInput] = useState(urlQuery)
  const [debouncedQuery, setDebouncedQuery] = useState(urlQuery)

  useEffect(() => {
    const id = setTimeout(() => setDebouncedQuery(searchInput), SEARCH_DEBOUNCE_MS)
    return () => clearTimeout(id)
  }, [searchInput])

  const updateUrlQuery = useCallback(
    (next: string) => {
      const params = new URLSearchParams(searchParams)
      if (next === '') params.delete(SEARCH_QUERY_KEY)
      else params.set(SEARCH_QUERY_KEY, next)
      setSearchParams(params, { replace: true })
    },
    [searchParams, setSearchParams],
  )

  // Write back to URL whenever the debounced value changes.
  useEffect(() => {
    if (debouncedQuery === urlQuery) return
    updateUrlQuery(debouncedQuery)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [debouncedQuery])

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    getTrainingRuns(1, PAGE_LIMIT)
      .then(res => {
        if (cancelled) return
        setRuns(res.data)
        setError(null)
      })
      .catch(err => {
        if (cancelled) return
        setError(err instanceof Error ? err.message : 'Failed to load training runs')
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => { cancelled = true }
  }, [])

  const filteredRuns = useMemo(() => {
    const q = debouncedQuery.trim().toLowerCase()
    if (q === '') return runs
    return runs.filter(r => r.title.toLowerCase().includes(q))
  }, [runs, debouncedQuery])

  const hasQuery = debouncedQuery.trim() !== ''

  return (
    <div className="training-run-list">
      <header className="training-run-list-header">
        <h2 className="training-run-list-title">Training History</h2>
        <label className="training-run-list-search">
          <span className="sr-only">학습 제목 검색</span>
          <input
            type="search"
            className="training-run-list-search-input"
            placeholder="제목 검색…"
            value={searchInput}
            onChange={e => setSearchInput(e.target.value)}
            aria-label="Search training runs by title"
          />
        </label>
      </header>

      {error && (
        <div className="training-run-list-error alert-error" role="alert">
          {error}
        </div>
      )}

      {loading ? (
        <div className="training-run-list-loading" role="status" aria-live="polite">
          Loading training runs…
        </div>
      ) : filteredRuns.length === 0 ? (
        <EmptyState query={hasQuery ? debouncedQuery : null} onClear={() => {
          setSearchInput('')
          updateUrlQuery('')
        }} />
      ) : (
        <>
          {/* Desktop table. Hidden on <768px via CSS. */}
          <div className="training-run-list-table-wrapper card">
            <table className="training-run-list-table" aria-label="Training runs">
              <thead>
                <tr>
                  <th scope="col">Title</th>
                  <th scope="col">Started</th>
                  <th scope="col">Status</th>
                  <th scope="col">Games</th>
                  <th scope="col">Win Rate</th>
                  <th scope="col">Avg Rally</th>
                </tr>
              </thead>
              <tbody>
                {filteredRuns.map(run => (
                  <RunRow key={run.title} run={run} query={debouncedQuery} />
                ))}
              </tbody>
            </table>
          </div>

          {/* Mobile card stack. Hidden on ≥768px via CSS. */}
          <div className="training-run-list-cards">
            {filteredRuns.map(run => (
              <RunCard key={run.title} run={run} query={debouncedQuery} />
            ))}
          </div>
        </>
      )}
    </div>
  )
}

interface RunRowProps {
  run: TrainingRun
  query: string
}

function RunRow({ run, query }: RunRowProps) {
  return (
    <tr className="training-run-list-row">
      <td className="training-run-list-cell-title">
        <Link
          to={`/history/${encodeURIComponent(run.title)}`}
          className="training-run-list-title-link"
        >
          <HighlightedText text={run.title} query={query} />
        </Link>
      </td>
      <td className="training-run-list-cell-started">
        {run.startedAt ? formatKstDateTime(run.startedAt) : '—'}
      </td>
      <td>
        <StatusChip status={run.status} />
      </td>
      <td className="training-run-list-cell-numeric">
        {run.totalGames.toLocaleString()}
      </td>
      <td className="training-run-list-cell-numeric">
        <WinRateBar rate={run.winRate} />
      </td>
      <td className="training-run-list-cell-numeric">
        {run.avgRallyLength.toFixed(1)}
      </td>
    </tr>
  )
}

function RunCard({ run, query }: RunRowProps) {
  return (
    <Link
      to={`/history/${encodeURIComponent(run.title)}`}
      className="training-run-card card"
    >
      <div className="training-run-card-row-1">
        <span className="training-run-card-title">
          <HighlightedText text={run.title} query={query} />
        </span>
        <StatusChip status={run.status} />
      </div>
      <div className="training-run-card-row-2 text-muted">
        <span>{run.startedAt ? formatKstDateTime(run.startedAt) : '—'}</span>
        <span> · {run.totalGames.toLocaleString()} games</span>
      </div>
      <div className="training-run-card-row-3">
        <WinRateBar rate={run.winRate} />
      </div>
    </Link>
  )
}

function StatusChip({ status }: { status: string }) {
  const normalized: 'running' | 'done' | 'stopped' =
    status === 'running'
      ? 'running'
      : status === 'stopped'
        ? 'stopped'
        : 'done'
  const label = normalized === 'running' ? 'Running' : normalized === 'stopped' ? 'Stopped' : 'Finished'
  return (
    <span
      className={`training-run-status-chip training-run-status-chip--${normalized}`}
      aria-label={`Run status: ${label}`}
    >
      {label}
    </span>
  )
}

function WinRateBar({ rate }: { rate: number }) {
  const pct = Math.max(0, Math.min(1, rate))
  return (
    <span className="training-run-winrate" aria-label={`Win rate ${(pct * 100).toFixed(1)}%`}>
      <span className="training-run-winrate-value">{(pct * 100).toFixed(1)}%</span>
      <span className="training-run-winrate-bar" aria-hidden="true">
        <span
          className="training-run-winrate-bar-fill"
          style={{ width: `${pct * 100}%` }}
        />
      </span>
    </span>
  )
}

/**
 * Highlight matched-substring fragments inside the title so users
 * can see *why* a row survived the search filter. Case-insensitive
 * match; safe against overlapping matches because `split` only
 * returns non-matching slices as unmatched text.
 */
function HighlightedText({ text, query }: { text: string; query: string }) {
  const q = query.trim()
  if (q === '') return <>{text}</>
  const regex = new RegExp(`(${escapeRegExp(q)})`, 'ig')
  const parts = text.split(regex)
  return (
    <>
      {parts.map((part, idx) =>
        part.toLowerCase() === q.toLowerCase() ? (
          <mark key={idx} className="training-run-highlight">{part}</mark>
        ) : (
          <span key={idx}>{part}</span>
        ),
      )}
    </>
  )
}

function escapeRegExp(s: string): string {
  return s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
}

interface EmptyStateProps {
  query: string | null
  onClear: () => void
}

function EmptyState({ query, onClear }: EmptyStateProps) {
  if (query !== null) {
    return (
      <div className="training-run-list-empty" role="status">
        <p>{`'${query}' 검색 결과가 없습니다.`}</p>
        <button type="button" className="training-run-list-clear" onClick={onClear}>
          검색 지우기
        </button>
      </div>
    )
  }
  return (
    <div className="training-run-list-empty" role="status">
      <p>학습 내역이 없습니다. 새 학습을 시작하면 여기에 나타납니다.</p>
      <Link to="/" className="training-run-list-cta btn btn-primary">
        학습 시작
      </Link>
    </div>
  )
}
