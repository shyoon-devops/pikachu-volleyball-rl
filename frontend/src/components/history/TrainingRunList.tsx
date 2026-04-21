import { memo, useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { getTrainingRuns, getModels, slugifyTitle } from '../../lib/api'
import type { TrainingRun } from '../../lib/types'
import { TimestampText } from '../shared/TimestampText'
import { RewardModelChip } from '../shared/RewardModelChip'
import { PolicyTypeChip } from '../shared/PolicyTypeChip'
import { useTrainingState } from '../../hooks/useTrainingState'
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

/**
 * Merge a fresh runs snapshot with the previously rendered list,
 * preserving the OLD object reference for any title whose scalar
 * fields are unchanged. This is load-bearing for FC-R7H: every
 * live refetch otherwise returns brand-new object references and
 * React.memo on the row component would see different props and
 * re-render every row — the exact churn we're trying to avoid.
 *
 * Equality here is shallow over the six aggregate fields. If BE
 * starts shipping nested objects the check needs to deepen.
 */
function runsShallowEqual(a: TrainingRun, b: TrainingRun): boolean {
  return (
    a.title === b.title &&
    a.experimentId === b.experimentId &&
    a.startedAt === b.startedAt &&
    a.endedAt === b.endedAt &&
    a.totalGames === b.totalGames &&
    a.winRate === b.winRate &&
    a.avgRallyLength === b.avgRallyLength &&
    a.status === b.status &&
    a.rewardModel === b.rewardModel &&
    a.policyType === b.policyType
  )
}

function mergeRuns(prev: TrainingRun[], next: TrainingRun[]): TrainingRun[] {
  const prevByTitle = new Map(prev.map(r => [r.title, r] as const))
  let anyChanged = prev.length !== next.length
  const merged = next.map(n => {
    const old = prevByTitle.get(n.title)
    if (old && runsShallowEqual(old, n)) return old
    anyChanged = true
    return n
  })
  return anyChanged ? merged : prev
}

/**
 * Route the per-row link to. Defaults to the history drill-down
 * (`/history/`) so existing callers stay unchanged; the evaluation
 * page passes `/evaluation/` (FC-R7C) to reuse the same L1 surface
 * with an eval-intent destination. CTA in the empty state still
 * points at `/` — starting a new training is the only escape hatch
 * regardless of which L1 surface the user is on.
 *
 * `mode` toggles the eval-intent variant (FC-R7F, 2026-04-18):
 *   - 'history'     — default labels + columns (back-compat).
 *   - 'evaluation'  — "Select Training for Evaluation" title, a
 *                     "Checkpoints" column showing per-run model
 *                     count, zero-checkpoint rows disabled + tooltip.
 * The count map is derived from a single `/api/models` fetch on
 * mount (no filter → whole inventory) bucketed by filename slug,
 * so we avoid N-per-row requests.
 */
export type TrainingRunListMode = 'history' | 'evaluation'

export interface TrainingRunListProps {
  linkBase?: string
  mode?: TrainingRunListMode
}

export function TrainingRunList({
  linkBase = '/history/',
  mode = 'history',
}: TrainingRunListProps = {}) {
  const [searchParams, setSearchParams] = useSearchParams()
  const { gameResultSeq } = useTrainingState()
  const [runs, setRuns] = useState<TrainingRun[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  // FC-R7F: per-title checkpoint counts for the evaluation variant.
  // `null` = never fetched (history mode); `Map` = fetched.
  const [checkpointCounts, setCheckpointCounts] = useState<Map<string, number> | null>(null)

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

  // FC-R7B live-history: refetch whenever a new game:result lands so
  // the run aggregates (totalGames / winRate / avgRally / running-status)
  // reflect the in-progress training run without a manual refresh. The
  // hook bumps `gameResultSeq` on every ws `game:result` message; adding
  // it to the dep array re-runs this effect.
  //
  // FC-R7H: never flip `loading` back to true on a live refetch — that
  // blanks the whole table with the "Loading…" placeholder for ~100ms,
  // producing a visible flicker with every game end. Only show the
  // placeholder until the first fetch lands; after that we swap data
  // in place and let `mergeRuns` reuse old object refs so React.memo
  // on RunRow/RunCard can skip unchanged rows.
  const initialLoadedRef = useRef(false)
  useEffect(() => {
    let cancelled = false
    if (!initialLoadedRef.current) setLoading(true)
    getTrainingRuns(1, PAGE_LIMIT)
      .then(res => {
        if (cancelled) return
        setRuns(prev => mergeRuns(prev, res.data))
        setError(null)
        initialLoadedRef.current = true
      })
      .catch(err => {
        if (cancelled) return
        setError(err instanceof Error ? err.message : 'Failed to load training runs')
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => { cancelled = true }
  }, [gameResultSeq])

  // FC-R7F: checkpoint-count fetch (evaluation mode only). One REST
  // call to the unfiltered models endpoint gives us every file's slug;
  // we bucket client-side into a Map<slug, count>. Re-runs on every
  // game:result bump so checkpoints that land mid-session become
  // clickable without a manual refresh. BE could expose
  // `checkpoint_count` on /training/runs directly per spec §4; until
  // then this one-off bucket fetch is cheaper than N filtered calls.
  useEffect(() => {
    if (mode !== 'evaluation') {
      setCheckpointCounts(null)
      return
    }
    let cancelled = false
    getModels()
      .then(models => {
        if (cancelled) return
        const map = new Map<string, number>()
        for (const m of models) {
          const slug = m.slug ?? null
          if (!slug) continue
          map.set(slug, (map.get(slug) ?? 0) + 1)
        }
        setCheckpointCounts(map)
      })
      .catch(() => {
        // Best-effort — a models fetch failure degrades to "count
        // unavailable" (the `Checkpoints` column renders `—`). The
        // row still links through in case BE reports but FE can't
        // read, so we don't block the user from clicking.
        if (!cancelled) setCheckpointCounts(new Map())
      })
    return () => { cancelled = true }
  }, [mode, gameResultSeq])

  const filteredRuns = useMemo(() => {
    const q = debouncedQuery.trim().toLowerCase()
    if (q === '') return runs
    // FC-R7A null-safety: a runs-aggregate row with `title: null`
    // would crash `r.title.toLowerCase()`. Treat null/missing as
    // the empty string so the search gracefully excludes them.
    return runs.filter(r => (r.title ?? '').toLowerCase().includes(q))
  }, [runs, debouncedQuery])

  const hasQuery = debouncedQuery.trim() !== ''

  const isEvalMode = mode === 'evaluation'
  const headerTitle = isEvalMode ? 'Select Training for Evaluation' : 'Training History'
  const variantClass = isEvalMode ? ' training-run-list--evaluation' : ''

  // Helper: resolve the checkpoint count for a given run by slug-
  // matching its title. Returns null when the count map isn't loaded
  // yet (shows `…` placeholder in the UI).
  const resolveCount = (title: string | null | undefined): number | null => {
    if (!checkpointCounts) return null
    if (!title) return 0
    const slug = slugifyTitle(title)
    return checkpointCounts.get(slug) ?? 0
  }

  return (
    <div className={`training-run-list${variantClass}`}>
      <header className="training-run-list-header">
        <h2 className="training-run-list-title">{headerTitle}</h2>
        <label className="training-run-list-search">
          <span className="sr-only">Search training runs by title</span>
          <input
            type="search"
            className="training-run-list-search-input"
            placeholder="Search title…"
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
            <table className="training-run-list-table" aria-label={isEvalMode ? 'Training runs (evaluation)' : 'Training runs'}>
              <thead>
                <tr>
                  <th scope="col">Title</th>
                  <th scope="col">Started</th>
                  <th scope="col">Status</th>
                  {isEvalMode && <th scope="col">Checkpoints</th>}
                  <th scope="col">Games</th>
                  <th scope="col">Win Rate</th>
                  <th scope="col">Avg Rally</th>
                </tr>
              </thead>
              <tbody>
                {filteredRuns.map(run => (
                  <RunRow
                    key={run.title}
                    run={run}
                    query={debouncedQuery}
                    linkBase={linkBase}
                    evalMode={isEvalMode}
                    checkpointCount={isEvalMode ? resolveCount(run.title) : null}
                  />
                ))}
              </tbody>
            </table>
          </div>

          {/* Mobile card stack. Hidden on ≥768px via CSS. */}
          <div className="training-run-list-cards">
            {filteredRuns.map(run => (
              <RunCard
                key={run.title}
                run={run}
                query={debouncedQuery}
                linkBase={linkBase}
                evalMode={isEvalMode}
                checkpointCount={isEvalMode ? resolveCount(run.title) : null}
              />
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
  linkBase: string
  evalMode?: boolean
  /** Per-run checkpoint count. `null` means "not yet loaded" (show `…`). */
  checkpointCount?: number | null
}

const RunRow = memo(function RunRow({ run, query, linkBase, evalMode = false, checkpointCount = null }: RunRowProps) {
  // FC-R7A null-safety: every scalar falls back to a safe value
  // before any method access. BE sends `null` for untitled legacy
  // records + empty aggregates; a null `title.toLowerCase()` or
  // `totalGames.toLocaleString()` crashes the whole table otherwise.
  const safeTitle = run.title && run.title.trim() !== '' ? run.title : 'untitled'
  const safeTotalGames = run.totalGames ?? 0
  const safeWinRate = Number.isFinite(run.winRate) ? run.winRate : 0
  const safeAvgRally = Number.isFinite(run.avgRallyLength) ? run.avgRallyLength : 0
  const disabled = evalMode && checkpointCount === 0
  const rowClass = `training-run-list-row${disabled ? ' training-run-list-row--disabled' : ''}`
  const titleCell = disabled ? (
    <span
      className="training-run-list-title-disabled"
      title="No saved checkpoints"
      aria-disabled="true"
    >
      <HighlightedText text={safeTitle} query={query} />
    </span>
  ) : (
    <Link
      to={`${linkBase}${encodeURIComponent(safeTitle)}`}
      className="training-run-list-title-link"
    >
      <HighlightedText text={safeTitle} query={query} />
    </Link>
  )
  return (
    <tr className={rowClass}>
      <td className="training-run-list-cell-title">
        {titleCell}
        {/* Reward-model chip — 8 px gap, right of title
            (DESIGN-REWARD-MODEL-SELECTOR.md §4). */}
        <span className="training-run-list-reward-chip">
          <RewardModelChip value={run.rewardModel} />
        </span>
        {/* Policy-type chip — 4 px gap, right of reward chip
            (DESIGN-POLICY-TYPE-SELECTOR.md §4). */}
        <span className="training-run-list-policy-chip">
          <PolicyTypeChip value={run.policyType} />
        </span>
      </td>
      <td className="training-run-list-cell-started">
        <TimestampText ts={run.startedAt} />
      </td>
      <td>
        <StatusChip status={run.status ?? 'done'} />
      </td>
      {evalMode && (
        <td className="training-run-list-cell-numeric">
          <CheckpointCountBadge count={checkpointCount} />
        </td>
      )}
      <td className="training-run-list-cell-numeric">
        {safeTotalGames.toLocaleString()}
      </td>
      <td className="training-run-list-cell-numeric">
        <WinRateBar rate={safeWinRate} />
      </td>
      <td className="training-run-list-cell-numeric">
        {safeAvgRally.toFixed(1)}
      </td>
    </tr>
  )
})

function CheckpointCountBadge({ count }: { count: number | null }) {
  if (count === null) {
    return <span className="training-run-list-checkpoints training-run-list-checkpoints--loading">…</span>
  }
  const kind = count === 0 ? 'zero' : 'some'
  return (
    <span
      className={`training-run-list-checkpoints training-run-list-checkpoints--${kind}`}
      aria-label={`${count} checkpoint${count === 1 ? '' : 's'}`}
      title={count === 0 ? 'No saved checkpoints' : undefined}
    >
      {count}
    </span>
  )
}

const RunCard = memo(function RunCard({ run, query, linkBase, evalMode = false, checkpointCount = null }: RunRowProps) {
  // Same null-safety as RunRow — mobile card stack reuses the
  // same fallback rules.
  const safeTitle = run.title && run.title.trim() !== '' ? run.title : 'untitled'
  const safeTotalGames = run.totalGames ?? 0
  const safeWinRate = Number.isFinite(run.winRate) ? run.winRate : 0
  const disabled = evalMode && checkpointCount === 0
  const cardInner = (
    <>
      <div className="training-run-card-row-1">
        <span className="training-run-card-title">
          <HighlightedText text={safeTitle} query={query} />
          <span className="training-run-list-reward-chip">
            <RewardModelChip value={run.rewardModel} />
          </span>
          <span className="training-run-list-policy-chip">
            <PolicyTypeChip value={run.policyType} />
          </span>
        </span>
        <StatusChip status={run.status ?? 'done'} />
      </div>
      <div className="training-run-card-row-2 text-muted">
        <span><TimestampText ts={run.startedAt} /></span>
        <span> · {safeTotalGames.toLocaleString()} games</span>
        {evalMode && (
          <>
            {' · '}
            <CheckpointCountBadge count={checkpointCount} />
          </>
        )}
      </div>
      <div className="training-run-card-row-3">
        <WinRateBar rate={safeWinRate} />
      </div>
    </>
  )
  if (disabled) {
    return (
      <div
        className="training-run-card card training-run-card--disabled"
        title="No saved checkpoints"
        aria-disabled="true"
      >
        {cardInner}
      </div>
    )
  }
  return (
    <Link
      to={`${linkBase}${encodeURIComponent(safeTitle)}`}
      className="training-run-card card"
    >
      {cardInner}
    </Link>
  )
})

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
  // FC-R7A: guard against callers that haven't yet filtered nulls.
  const safeText = text ?? ''
  const q = query.trim()
  if (q === '') return <>{safeText}</>
  const regex = new RegExp(`(${escapeRegExp(q)})`, 'ig')
  const parts = safeText.split(regex)
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
        <p>{`No results for '${query}'.`}</p>
        <button type="button" className="training-run-list-clear" onClick={onClear}>
          Clear search
        </button>
      </div>
    )
  }
  return (
    <div className="training-run-list-empty" role="status">
      <p>No training runs yet. Start a new one and it will appear here.</p>
      <Link to="/" className="training-run-list-cta btn btn-primary">
        Start Training
      </Link>
    </div>
  )
}
