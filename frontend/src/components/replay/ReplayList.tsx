import { memo, useState, useEffect, useMemo, useCallback, useRef } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { getGames, getAvailableReplays } from '../../lib/api'
import { useTrainingState } from '../../hooks/useTrainingState'
import type { GameRecord, ReplayInfo } from '../../lib/types'

/**
 * FC-R7H: merge a fresh games snapshot with the previously rendered
 * list, preserving OLD object references for rows whose scalar
 * fields are unchanged. Keeps the memoized <GameRow> from re-
 * rendering every row on a live refetch — the main source of the
 * reported flicker.
 */
function gamesShallowEqual(a: GameRecord, b: GameRecord): boolean {
  return (
    a.id === b.id &&
    a.gameId === b.gameId &&
    a.timestamp === b.timestamp &&
    a.score1 === b.score1 &&
    a.score2 === b.score2 &&
    a.winner === b.winner &&
    a.durationFrames === b.durationFrames &&
    a.rallyCount === b.rallyCount &&
    a.envId === b.envId &&
    a.episode === b.episode &&
    a.title === b.title &&
    a.botLevel === b.botLevel &&
    a.experimentId === b.experimentId
  )
}

function mergeGames(prev: GameRecord[], next: GameRecord[]): GameRecord[] {
  // Use gameId as the merge key when present (the UUID4 set at
  // game-end); fall back to Mongo ObjectId for legacy rows.
  const keyOf = (g: GameRecord) => g.gameId ?? g.id
  const prevByKey = new Map(prev.map(g => [keyOf(g), g] as const))
  let anyChanged = prev.length !== next.length
  const merged = next.map(n => {
    const old = prevByKey.get(keyOf(n))
    if (old && gamesShallowEqual(old, n)) return old
    anyChanged = true
    return n
  })
  return anyChanged ? merged : prev
}
import {
  formatBotLevel,
  formatRallyCount,
  formatAvgRallyLength,
  formatExperimentIdShort,
  formatEnvId,
  formatEpisode,
} from '../../lib/formatGame'
import { formatKstDateTime } from '../../lib/formatTime'
import './ReplayList.css'

const PAGE_LIMIT = 20

/**
 * Default env count for the filter dropdown. Matches the
 * `DEFAULT_N_ENVS` on the Dashboard (Designer spec §1). Hardcoded
 * because `/api/training/status` doesn't currently expose `n_envs`;
 * if BE adds it later, swap this for a fetched value.
 */
const DEFAULT_N_ENVS = 8

/** URL query parameter key for the env filter (spec §6: `?env=N`). */
const ENV_QUERY_KEY = 'env'

/**
 * Parse `?env=...` into a canonical filter token. BE emits env_id as
 * a STRING ("0".."7" for parallel envs, "demo" for the standalone
 * game — see `backend/rl/callbacks.py`), so the filter compares
 * string-vs-string. Accepts:
 *   ?env=3    → "3"      (matches ENV 3 rows)
 *   ?env=demo → "demo"   (matches the demo-game row)
 *   absent / bogus → null (= All)
 */
function parseEnvParam(raw: string | null): string | null {
  if (raw === null) return null
  const trimmed = raw.trim()
  if (trimmed === '') return null
  if (trimmed.toLowerCase() === 'demo') return 'demo'
  if (/^\d+$/.test(trimmed)) return trimmed
  return null
}

/**
 * Unified game-history view (B2, 2026-04-18).
 *
 * Previously the page had two parallel surfaces — an "Available
 * Replays" card grid driven by `/api/replays` plus a paginated
 * `/api/games` table — and the user had to mentally join the two by
 * `gameId`. Now both endpoints are fetched in parallel and merged
 * into a single per-row view: each `GameRecord` carries a "Watch"
 * action when a replay file exists for its `id`.
 *
 * Why we still hit both endpoints:
 *   - `/api/games`     — authoritative metadata (timestamp, scores,
 *                        winner, durationFrames, rallyCount, botLevel)
 *   - `/api/replays`   — filesystem inventory (which `gameId`s have a
 *                        playable .msgpack on disk)
 * They live in different stores (Mongo vs filesystem), so no single
 * endpoint can answer "give me games + their replay availability".
 * Two parallel REST calls is cheap.
 *
 * Failure mode: if the replays endpoint fails, we still render games
 * without the Watch column lighting up (no replay link). The error
 * banner only appears for a games-fetch failure, since that's the
 * only data the table can't render around.
 */
export interface ReplayListProps {
  /**
   * Scope the page to a single training run (R6H, spec §2). When
   * set, the component fetches `getGames(page, limit, titleFilter)`
   * so BE filters server-side. Mostly used by
   * `TrainingRunDetail` — when omitted the component behaves as
   * the legacy unified history list.
   */
  titleFilter?: string
  /**
   * Hide the Title column (R6H, §2b — redundant once the scope is
   * already a single run). Defaults to false (unfiltered list
   * keeps the column).
   */
  hideTitleColumn?: boolean
  /**
   * Override the "no games" empty-state message. Level-2 uses
   * "이 학습에는 아직 기록된 게임이 없습니다." per §2c; unfiltered
   * view keeps the generic "No games recorded yet." default.
   */
  emptyStateOverride?: string
}

export function ReplayList({
  titleFilter,
  hideTitleColumn = false,
  emptyStateOverride,
}: ReplayListProps = {}) {
  const navigate = useNavigate()
  const [searchParams, setSearchParams] = useSearchParams()
  // FC-R7B live-history: bumps on each ws `game:result`; added to the
  // fetch effect's deps so the table pulls fresh `/api/games` data as
  // new games land, mirroring TrainingRunList.
  const { gameResultSeq } = useTrainingState()
  const [games, setGames] = useState<GameRecord[]>([])
  const [replays, setReplays] = useState<ReplayInfo[]>([])
  const [page, setPage] = useState(1)
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  /**
   * Env filter sourced from the URL query (`?env=N`) so the state is
   * shareable via copy-paste — spec §6. `null` = show all envs.
   * Writes go back through `setSearchParams` with `replace: true` so
   * filter toggles don't clutter the browser history.
   */
  const envFilter = parseEnvParam(searchParams.get(ENV_QUERY_KEY))

  const setEnvFilter = useCallback(
    (next: string | null) => {
      const params = new URLSearchParams(searchParams)
      if (next === null) {
        params.delete(ENV_QUERY_KEY)
      } else {
        params.set(ENV_QUERY_KEY, next)
      }
      setSearchParams(params, { replace: true })
    },
    [searchParams, setSearchParams],
  )

  // FC-R7H: `setLoading(true)` on every live refetch flashed the whole
  // table with the "Loading..." placeholder for ~100ms — the exact
  // flicker users reported. Only flip loading to true on the first
  // fetch; subsequent live refetches (gameResultSeq bumps) swap data
  // in place and let `mergeGames` preserve old object refs so the
  // memoized row component skips unchanged rows.
  const initialLoadedRef = useRef(false)
  useEffect(() => {
    let cancelled = false
    if (!initialLoadedRef.current) setLoading(true)
    // `Promise.all` short-circuits on the first rejection — using
    // `.catch(() => [])` on the replays call lets games still render
    // when the filesystem inventory endpoint hiccups.
    Promise.all([
      // R6H: `titleFilter` forwards to BE `GET /api/games?title=X`
      // (T5 fc38f3d8). When omitted the endpoint returns the
      // unified list.
      getGames(page, PAGE_LIMIT, titleFilter),
      getAvailableReplays().catch(() => [] as ReplayInfo[]),
    ])
      .then(([gamesRes, replaysRes]) => {
        if (cancelled) return
        setGames(prev => mergeGames(prev, gamesRes.data))
        setTotal(gamesRes.total)
        setReplays(replaysRes)
        setError(null)
        initialLoadedRef.current = true
      })
      .catch(err => {
        if (cancelled) return
        setError(err instanceof Error ? err.message : 'Failed to load games')
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => { cancelled = true }
  }, [page, titleFilter, gameResultSeq])

  /**
   * Build a `Map<gameId, ReplayInfo>` once per replays change so the
   * per-row lookup in the table body stays O(1). Recomputing inside
   * the row map() would be O(N²) on long pages.
   */
  const replayByGameId = useMemo(() => {
    const m = new Map<string, ReplayInfo>()
    for (const r of replays) m.set(r.gameId, r)
    return m
  }, [replays])

  /**
   * Client-side env filter. Applied AFTER the REST fetch because the
   * BE list endpoint doesn't take an env query param today. Games
   * with an undefined envId NEVER match a concrete filter — they
   * only appear when the filter is "All". Keeps the pagination total
   * accurate for the unfiltered view; the filtered-count hint shows
   * how many rows the current page is actually rendering.
   */
  const filteredGames = useMemo(() => {
    if (envFilter === null) return games
    // BE emits env_id as a string; filter comparison is string===string.
    return games.filter(g => g.envId === envFilter)
  }, [games, envFilter])

  /**
   * Env id options for the filter dropdown. Combines:
   *   - The DEFAULT_N_ENVS baseline (ENV 0..7) so the dropdown is
   *     never emptier than expected on an empty page.
   *   - Every numeric env_id actually observed in the fetched games
   *     list, so runs with n_envs > 8 show their upper slots
   *     (FC-R6E user report, 2026-04-18).
   * Demo is appended separately — BE's "demo" string sits outside
   * the numeric range.
   *
   * Sorted ascending by numeric value so the dropdown reads
   * naturally. [BE-WAITING] Adding `n_envs` to
   * `/api/training/status` would let us pick up the run-configured
   * count even when zero games have landed yet; until then the
   * baseline covers that empty-page window.
   */
  const envOptions = useMemo(() => {
    const ids = new Set<number>()
    for (let i = 0; i < DEFAULT_N_ENVS; i++) ids.add(i)
    for (const g of games) {
      if (g.envId === undefined || g.envId === null) continue
      const n = Number(g.envId)
      if (Number.isFinite(n) && Number.isInteger(n) && n >= 0) {
        ids.add(n)
      }
    }
    return Array.from(ids).sort((a, b) => a - b)
  }, [games])

  /** True when at least one fetched game is tagged `"demo"`. */
  const demoSeen = useMemo(
    () => games.some(g => g.envId === 'demo'),
    [games],
  )

  /** Column count — shrinks by 1 when the Title column is hidden. */
  const columnCount = hideTitleColumn ? 11 : 12

  const totalPages = Math.max(1, Math.ceil(total / PAGE_LIMIT))

  const changePage = (next: number) => {
    setPage(next)
  }

  return (
    <div className="replay-list">
      <h2 className="replay-list-title">Game History</h2>

      {error && (
        <div className="replay-list-error alert-error">{error}</div>
      )}

      <div className="replay-list-filter-bar" role="group" aria-label="Filter controls">
        <label className="replay-list-filter-label">
          Env
          <select
            className="replay-list-filter-select"
            value={envFilter ?? 'all'}
            onChange={e => {
              const v = e.target.value
              setEnvFilter(v === 'all' ? null : v)
            }}
            aria-label="Filter by parallel env"
          >
            <option value="all">All</option>
            {envOptions.map(i => (
              <option key={i} value={String(i)}>ENV {i}</option>
            ))}
            {/*
              Demo option — always show it when any game in the
              current page has env_id === "demo" (so it's discoverable
              for mixed-mode runs); keep it hidden otherwise so
              parallel-only runs don't see a dangling option.
            */}
            {demoSeen && <option value="demo">DEMO</option>}
          </select>
        </label>
        {envFilter !== null && (
          <span className="replay-list-filter-hint">
            Showing {filteredGames.length} row{filteredGames.length === 1 ? '' : 's'} with env_id={envFilter}
          </span>
        )}
      </div>

      <div className="replay-list-table-wrapper card table-scroll">
        <table className="replay-list-table">
          <thead>
            <tr>
              {([
                ['Date'],
                // FC-R6G: Title column (Dashboard's Recent Games
                // mirror). Redundant in level-2 drill-down where
                // the page is already scoped to one run — hidden
                // there via the `hideTitleColumn` prop (R6H §2b).
                ...(hideTitleColumn ? [] : [['Title'] as [string]]),
                ['Env'],
                // FC-R6D: em-dash values are BE-WAITING — GameRecord
                // has no `episode` field yet. Tooltip explains to
                // avoid "this is broken" confusion.
                ['Episode', 'Pending BE support — field not yet saved per game'],
                ['Bot Level'],
                ['Score'],
                ['Winner'],
                ['Frames'],
                ['Rallies'],
                ['Avg Rally'],
                ['Experiment'],
                ['Replay'],
              ] as Array<[string, string?]>).map(([h, tip]) => (
                <th key={h} scope="col" title={tip}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr>
                <td colSpan={columnCount} className="replay-list-empty">Loading...</td>
              </tr>
            ) : filteredGames.length === 0 ? (
              <tr>
                <td colSpan={columnCount} className="replay-list-empty empty-state">
                  {envFilter !== null
                    ? `No games match env_id=${envFilter} on this page.`
                    : emptyStateOverride ?? 'No games recorded yet.'}
                </td>
              </tr>
            ) : (
              filteredGames.map(g => {
                const joinKey = g.gameId ?? g.id
                const replay = replayByGameId.get(joinKey) ?? null
                return (
                  <GameRow
                    key={g.id}
                    game={g}
                    replay={replay}
                    hideTitleColumn={hideTitleColumn}
                    onWatch={() => navigate(`/replay/${joinKey}`)}
                  />
                )
              })
            )}
          </tbody>
        </table>
      </div>

      {totalPages > 1 && (
        <div className="replay-list-pagination">
          <button
            onClick={() => changePage(Math.max(1, page - 1))}
            disabled={page <= 1}
            className="replay-list-page-btn btn btn-ghost"
          >
            Prev
          </button>
          <span className="replay-list-page-info">
            {page} / {totalPages}
          </span>
          <button
            onClick={() => changePage(Math.min(totalPages, page + 1))}
            disabled={page >= totalPages}
            className="replay-list-page-btn btn btn-ghost"
          >
            Next
          </button>
        </div>
      )}
    </div>
  )
}

interface GameRowProps {
  game: GameRecord
  replay: ReplayInfo | null
  hideTitleColumn: boolean
  onWatch: () => void
}

/**
 * FC-R7H: memoized row. The parent re-renders on every `gameResultSeq`
 * bump, but `mergeGames` preserves the prior row's `GameRecord`
 * reference for any row whose scalar fields are unchanged — so
 * `memo`'s default shallow prop check short-circuits the re-render
 * for existing rows. Only the freshly-landed row actually repaints.
 *
 * The `onWatch` callback is recreated on every parent render (arrow
 * in JSX), which would defeat the memo if the game data is the sole
 * stable prop. A custom comparator ignores `onWatch` since the
 * handler is content-neutral (it just navigates to this row's id).
 */
const GameRow = memo(
  function GameRow({ game: g, replay, hideTitleColumn, onWatch }: GameRowProps) {
    const joinKey = g.gameId ?? g.id
    return (
      <tr>
        <td>{formatKstDateTime(g.timestamp)}</td>
        {hideTitleColumn ? null : (
          <td className="replay-list-title-cell" title={g.title ?? undefined}>
            {g.title && g.title.trim() !== '' ? g.title : '—'}
          </td>
        )}
        <td>
          <span
            className={`env-chip${g.envId === undefined ? ' env-chip--empty' : ''}`}
            aria-label={g.envId === undefined ? 'No env id recorded' : `Env ${g.envId}`}
            data-env-id={g.envId ?? ''}
          >
            {formatEnvId(g.envId)}
          </span>
        </td>
        <td className="text-muted">{formatEpisode(g.episode)}</td>
        <td>{formatBotLevel(g.botLevel)}</td>
        <td className="score-cell">
          <span className="score-p1">{g.score1}</span>
          {' : '}
          <span className="score-p2">{g.score2}</span>
        </td>
        <td className={g.winner === 1 ? 'winner-agent' : 'winner-bot'}>
          {g.winner === 1 ? 'RL Agent' : 'Bot'}
        </td>
        <td className="text-muted">{g.durationFrames}</td>
        <td className="text-muted">{formatRallyCount(g.rallyCount)}</td>
        <td className="text-muted">
          {formatAvgRallyLength(g.durationFrames, g.rallyCount)}
        </td>
        <td className="text-muted text-mono" title={g.experimentId ?? undefined}>
          {formatExperimentIdShort(g.experimentId)}
        </td>
        <td>
          {replay ? (
            <button
              type="button"
              className="replay-list-btn"
              onClick={onWatch}
              aria-label={`Watch replay for game ${joinKey.slice(0, 8)}`}
              title={`${(replay.sizeBytes / 1024).toFixed(0)}KB`}
            >
              Watch
            </button>
          ) : (
            <span className="text-muted" aria-label="No replay file available">—</span>
          )}
        </td>
      </tr>
    )
  },
  (prev, next) =>
    prev.hideTitleColumn === next.hideTitleColumn &&
    prev.replay === next.replay &&
    prev.game === next.game,
  // Intentionally omits `onWatch` from the comparator — the callback
  // reference changes on every parent render but the behaviour is
  // bound to game.id, which the game prop guard already pins.
)
