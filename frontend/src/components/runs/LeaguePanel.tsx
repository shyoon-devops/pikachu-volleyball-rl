import { useEffect, useMemo, useState } from 'react'
import { getLeagueStandings } from '../../lib/api'
import { useTrainingState } from '../../hooks/useTrainingState'
import type { LeagueCheckpoint, LeagueStandings } from '../../lib/types'
import { TimestampText } from '../shared/TimestampText'
import './LeaguePanel.css'

/**
 * League sub-tab body (v2.x Sprint 1 — docs/design/SELF-PLAY-UX.md §2).
 *
 * Four stacked regions per spec:
 *   - Pool status bar: fill / champion / generation / mode
 *   - Top-10 leaderboard with champion row highlight
 *   - Recent league matches (last ~30 from the WS payload tail)
 *   - Elo progression chart [BE-WAITING — historical Elo series
 *     not yet exposed; render a note + a snapshot sparkline of the
 *     top-10 Elo distribution instead]
 *
 * Data sources:
 *   - REST `GET /api/league/standings?limit=10` on mount (covers
 *     the cold-refresh + idle cases).
 *   - WS `training:league_update` broadcast every 64 matches: the
 *     hook stores the latest payload on `leagueUpdate`, which
 *     overrides the REST snapshot for the top-N + recent-matches
 *     regions so the view stays live.
 */

const LEAGUE_POOL_CAP = 32

export function LeaguePanel() {
  const { leagueUpdate } = useTrainingState()
  const [rest, setRest] = useState<LeagueStandings | null>(null)
  const [restError, setRestError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    getLeagueStandings(10)
      .then(s => { if (!cancelled) setRest(s) })
      .catch(err => {
        if (cancelled) return
        setRestError(err instanceof Error ? err.message : 'Failed to load standings')
      })
    return () => { cancelled = true }
  }, [])

  // Merge policy: the WS payload is authoritative while running
  // (newer snapshot); REST fills in the fields WS doesn't carry
  // (total_checkpoints) and provides the first render before any
  // match has broadcast.
  const top: LeagueCheckpoint[] = leagueUpdate?.topN ?? rest?.top ?? []
  const poolFilled = leagueUpdate?.poolSize ?? rest?.totalCheckpoints ?? 0
  const championId = leagueUpdate?.championId ?? rest?.championId ?? null
  const generation = leagueUpdate?.generation ?? rest?.generation ?? 0
  const recent = leagueUpdate?.recent ?? []

  const poolPercent = useMemo(
    () => Math.min(100, Math.round((poolFilled / LEAGUE_POOL_CAP) * 100)),
    [poolFilled],
  )

  const eloRange = useMemo(() => {
    if (top.length === 0) return { min: 0, max: 0 }
    const elos = top.map(c => c.elo)
    return { min: Math.min(...elos), max: Math.max(...elos) }
  }, [top])

  const isEmpty = top.length === 0

  return (
    <div className="league-panel" aria-label="Self-play league">
      {restError && !leagueUpdate && (
        <div className="league-panel-error alert-error" role="alert">
          {restError}
        </div>
      )}

      {/* Pool status bar — sticky. */}
      <section className="league-pool-status" aria-label="Pool status">
        <div className="league-pool-status-bar">
          <div
            className="league-pool-status-fill"
            style={{ width: `${poolPercent}%` }}
            aria-hidden="true"
          />
        </div>
        <div className="league-pool-status-meta">
          <span className="league-pool-chip">{`${poolFilled} / ${LEAGUE_POOL_CAP}`}</span>
          <span className="league-pool-champion" title={championId ?? 'No champion yet'}>
            <span className="league-pool-champion-label">Champion:</span>{' '}
            <span className="league-pool-champion-id">
              {championId ? shortCheckpoint(championId) : '—'}
            </span>
          </span>
          <span className="league-pool-generation">{`Gen ${generation}`}</span>
          {isEmpty && (
            <span className="league-pool-empty-hint">
              Pool empty — falling back to rule ladder
            </span>
          )}
        </div>
      </section>

      {/* Top-10 leaderboard. */}
      <section className="league-leaderboard" aria-label="Top-10 leaderboard">
        <h3 className="league-section-title">Top 10</h3>
        {isEmpty ? (
          <p className="league-empty text-muted">
            No checkpoints admitted yet. The pool populates automatically on save.
          </p>
        ) : (
          <div className="league-leaderboard-wrapper card table-scroll">
            <table className="league-leaderboard-table" aria-label="Leaderboard">
              <thead>
                <tr>
                  <th scope="col" className="league-rank-col">#</th>
                  <th scope="col">Checkpoint</th>
                  <th scope="col">Elo</th>
                  <th scope="col">Games</th>
                  <th scope="col">Win %</th>
                  <th scope="col">Admitted</th>
                </tr>
              </thead>
              <tbody>
                {top.map((c, idx) => {
                  const isChampion = c.id === championId
                  const winRate = c.games > 0 ? c.wins / c.games : 0
                  return (
                    <tr
                      key={c.id}
                      className={`league-leaderboard-row${isChampion ? ' league-leaderboard-row--champion' : ''}`}
                    >
                      <td className="league-rank-col">{idx + 1}</td>
                      <td className="league-checkpoint-cell">
                        {isChampion && (
                          <span className="league-champion-crown" aria-label="Champion">
                            👑
                          </span>
                        )}
                        <span className="league-checkpoint-id" title={c.id}>
                          {shortCheckpoint(c.id)}
                        </span>
                        {c.source === 'anchor' && (
                          <span className="league-source-chip" title="Rule anchor (fixed Elo)">
                            anchor
                          </span>
                        )}
                      </td>
                      <td className="league-numeric">{Math.round(c.elo).toLocaleString()}</td>
                      <td className="league-numeric text-muted">
                        {c.games > 0 ? c.games.toLocaleString() : '—'}
                      </td>
                      <td className="league-numeric">
                        {c.games > 0 ? `${(winRate * 100).toFixed(1)}%` : '—'}
                      </td>
                      <td className="text-muted">
                        <TimestampText ts={c.admittedAt} />
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        )}
      </section>

      {/* Recent league matches (last ~30 from the WS tail). */}
      <section className="league-recent" aria-label="Recent league matches">
        <h3 className="league-section-title">Recent matches</h3>
        {recent.length === 0 ? (
          <p className="league-empty text-muted">
            {leagueUpdate
              ? 'No match records in the last broadcast window yet.'
              : 'Match history appears once the first league_update broadcast lands.'}
          </p>
        ) : (
          <div className="league-recent-wrapper card table-scroll">
            <table className="league-recent-table">
              <thead>
                <tr>
                  <th scope="col">Opponent</th>
                  <th scope="col">Winner</th>
                  <th scope="col">Duration</th>
                  <th scope="col">Δ Elo</th>
                </tr>
              </thead>
              <tbody>
                {recent.slice(0, 30).map((m, idx) => (
                  <tr key={`${m.opponentId}-${idx}`}>
                    <td className="league-checkpoint-id" title={m.opponentId}>
                      {shortCheckpoint(m.opponentId)}
                    </td>
                    <td className="text-muted">{m.winner ?? '—'}</td>
                    <td className="text-muted league-numeric">
                      {Number.isFinite(m.duration) ? `${m.duration} frames` : '—'}
                    </td>
                    <td className={`league-numeric league-delta-${m.deltaElo >= 0 ? 'up' : 'down'}`}>
                      {formatDelta(m.deltaElo)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      {/* Elo distribution snapshot — lightweight stand-in for the
          historical progression chart. BE-WAITING note explains the
          placeholder. */}
      <section className="league-chart" aria-label="Elo distribution (snapshot)">
        <h3 className="league-section-title">Elo distribution</h3>
        {isEmpty ? (
          <p className="league-empty text-muted">
            Elo records being collected — chart appears once checkpoints admit.
          </p>
        ) : (
          <div className="league-chart-card card">
            <div className="league-chart-range">
              <span className="text-muted">Min</span>
              <span className="league-numeric">{Math.round(eloRange.min)}</span>
              <span className="text-muted">· Max</span>
              <span className="league-numeric">{Math.round(eloRange.max)}</span>
            </div>
            <div className="league-chart-bars" role="presentation">
              {top.map(c => {
                const pct = eloRange.max === eloRange.min
                  ? 100
                  : Math.max(
                    4,
                    Math.round(((c.elo - eloRange.min) / (eloRange.max - eloRange.min)) * 100),
                  )
                return (
                  <div
                    key={c.id}
                    className={`league-chart-bar${c.id === championId ? ' league-chart-bar--champion' : ''}`}
                    style={{ height: `${pct}%` }}
                    title={`${shortCheckpoint(c.id)} — Elo ${Math.round(c.elo)}`}
                  />
                )
              })}
            </div>
            <p className="league-chart-note text-muted">
              Snapshot view. Historical Elo progression chart is BE-WAITING
              (requires per-step Elo series — tracked in ADR-0014 follow-up).
            </p>
          </div>
        )}
      </section>
    </div>
  )
}

/**
 * Checkpoints are identified by the 40+-char filename slug
 * `run-baseline__a3f9bc21__200000`. The leaderboard column is narrow;
 * we display the last two `__`-separated segments (`a3f9bc21__200000`)
 * which carry the useful identity — the exp8 short hash plus step.
 * Full id is exposed via `title` attribute for hover.
 */
function shortCheckpoint(id: string): string {
  const parts = id.split('__')
  if (parts.length >= 2) return parts.slice(-2).join('__')
  return id
}

function formatDelta(delta: number): string {
  if (!Number.isFinite(delta)) return '—'
  const abs = Math.abs(delta)
  const rounded = abs < 1 ? delta.toFixed(2) : Math.round(delta).toString()
  return delta >= 0 ? `+${rounded}` : rounded
}
