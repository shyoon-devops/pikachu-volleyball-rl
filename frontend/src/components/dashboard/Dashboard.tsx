import { useState } from 'react'
import { GameCanvas } from '../game/GameCanvas'
import { GameOverlay } from '../game/GameOverlay'
import { MetricsChart } from './MetricsChart'
import { TrainingControls } from './TrainingControls'
import { HyperparamForm } from './HyperparamForm'
import { DEFAULT_HYPERPARAMS } from './hyperparamDefaults'
import { DashboardSkeleton } from './DashboardSkeleton'
import { useTrainingState } from '../../hooks/useTrainingState'
import type { Hyperparams } from '../../lib/types'
import {
  formatBotLevel,
  formatRallyCount,
  formatAvgRallyLength,
  formatExperimentIdShort,
} from '../../lib/formatGame'
import { formatKstDateTime } from '../../lib/formatTime'
import './Dashboard.css'

export function Dashboard() {
  const { connectionState, reconnectAttempt, status, metrics, latestFrame, recentGames, send } = useTrainingState()

  // Hyperparams live at the Dashboard so the single Start button in
  // <TrainingControls /> can submit them. Do NOT re-introduce a second
  // Start button inside <HyperparamForm /> — we intentionally collapsed
  // the two into one CTA.
  //
  // bot_level is intentionally NOT held here (Option A, 2026-04-12): it
  // lives exclusively on ``status.botLevel`` — the L1–L5 buttons in
  // <TrainingControls /> mutate it via training:set_level, and the BE
  // dispatcher carries it over into training:start when the payload
  // omits ``bot_level`` (schemas.py:92, handlers.py:131-135).
  const [params, setParams] = useState<Hyperparams>(DEFAULT_HYPERPARAMS)

  const score1 = latestFrame?.score1 ?? 0
  const score2 = latestFrame?.score2 ?? 0
  const isStopped = status.state === 'stopped'

  // Show skeleton only on the very first connect attempt while we have no
  // data at all. After anything arrives (frame / metrics / recent games)
  // we keep the real UI up — even through reconnects — so the layout
  // doesn't flash back to skeletons mid-session. A persistent
  // disconnect should surface the reconnect banner, not a skeleton.
  const hasAnyData =
    latestFrame !== null || metrics.length > 0 || recentGames.length > 0
  const isInitialLoading = connectionState === 'connecting' && !hasAnyData
  if (isInitialLoading) {
    return <DashboardSkeleton />
  }

  const handleStart = () => {
    // Option A: bot_level omitted — BE uses status.bot_level (set via the
    // L1–L5 buttons in <TrainingControls />). Sending it here would
    // silently override a level the user just picked.
    send('training:start', { hyperparams: params })
  }

  return (
    <div className="dashboard">
      <section className="dashboard-left" aria-labelledby="dashboard-game-heading">
        <h2 id="dashboard-game-heading" className="sr-only">Game &amp; Controls</h2>
        <TrainingControls
          status={status}
          connectionState={connectionState}
          reconnectAttempt={reconnectAttempt}
          send={send}
          onStart={handleStart}
        />

        <div className="dashboard-game-wrapper" role="img" aria-label="Live game canvas — Pikachu Volleyball agent play">
          <GameCanvas gameState={latestFrame} />
          <GameOverlay score1={score1} score2={score2} />
          {!latestFrame && status.state === 'running' && (
            <div className="dashboard-game-waiting" role="status" aria-live="polite">
              Waiting for game frames...
            </div>
          )}
        </div>

        {isStopped && (
          <HyperparamForm
            params={params}
            onParamsChange={setParams}
            disabled={connectionState !== 'connected'}
          />
        )}
      </section>

      <section className="dashboard-right" aria-labelledby="dashboard-metrics-heading">
        <h2 id="dashboard-metrics-heading" className="sr-only">Training Metrics</h2>
        <MetricsChart data={metrics} dataKey="meanReward" color="#22c55e" label="Reward" currentStep={status.currentStep} />
        <MetricsChart data={metrics} dataKey="winRate" color="#3b82f6" label="Win Rate" currentStep={status.currentStep} />
        <MetricsChart data={metrics} dataKey="policyLoss" color="#ef4444" label="Policy Loss" currentStep={status.currentStep} />
        <MetricsChart data={metrics} dataKey="valueLoss" color="#f97316" label="Value Loss" currentStep={status.currentStep} />
      </section>

      <section className="dashboard-bottom" aria-labelledby="recent-games-heading">
        <div className="card">
          <h3 className="card-title" id="recent-games-heading">Recent Games</h3>
          {recentGames.length === 0 ? (
            <p className="recent-games-empty empty-state">No games yet.</p>
          ) : (
            <div className="recent-games table-scroll">
              <table className="recent-games-table" aria-labelledby="recent-games-heading">
                <thead>
                  <tr>
                    {/*
                      `#` rank column dropped (R2-empirical, 2026-04-18):
                      user reported the Time column's leading digit looked
                      gray even after `.text-muted` was removed from the
                      cell. Playwright inspection against dev bundle
                      UoTn_2Rz confirmed the Time cell actually renders at
                      primary color (rgb 26, 29, 41) — the "gray first
                      digit" was the `#` column's muted digit sitting 24px
                      to the left of "2026" in the same monospace font,
                      reading as a single token across the cell boundary.
                      Evidence screenshot in
                      docs/fe-evidence/r2-rank-illusion-dev-UoTn_2Rz.png.
                      The `#` column was also redundant with the row's
                      top-to-bottom ordering — dropping it kills the
                      adjacency at its source without loss of information.
                    */}
                    {[
                      'Time',
                      'Bot Level',
                      'Score',
                      'Winner',
                      'Frames',
                      'Rallies',
                      'Avg Rally',
                      'Experiment',
                    ].map(h => (
                      <th key={h} scope="col">{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {recentGames.slice(0, 20).map((g) => (
                    <tr key={g.id}>
                      <td>{formatKstDateTime(g.timestamp)}</td>
                      <td>{formatBotLevel(g.botLevel)}</td>
                      <td>
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
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </section>
    </div>
  )
}
