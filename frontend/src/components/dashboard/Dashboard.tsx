import { GameCanvas } from '../game/GameCanvas'
import { GameOverlay } from '../game/GameOverlay'
import { MetricsChart } from './MetricsChart'
import { TrainingControls } from './TrainingControls'
import { HyperparamForm } from './HyperparamForm'
import { useTrainingState } from '../../hooks/useTrainingState'
import type { Hyperparams } from '../../lib/types'
import './Dashboard.css'

export function Dashboard() {
  const { connectionState, reconnectAttempt, status, metrics, latestFrame, recentGames, send } = useTrainingState()

  const score1 = latestFrame?.score1 ?? 0
  const score2 = latestFrame?.score2 ?? 0
  const isStopped = status.state === 'stopped'

  const handleStart = (params: Hyperparams, botLevel: number) => {
    send('training:start', { hyperparams: params, bot_level: botLevel })
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
          onStartWithParams={handleStart}
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
          <HyperparamForm onSubmit={handleStart} disabled={connectionState !== 'connected'} />
        )}
      </section>

      <section className="dashboard-right" aria-labelledby="dashboard-metrics-heading">
        <h2 id="dashboard-metrics-heading" className="sr-only">Training Metrics</h2>
        <MetricsChart data={metrics} dataKey="meanReward" color="#22c55e" label="Reward" />
        <MetricsChart data={metrics} dataKey="winRate" color="#3b82f6" label="Win Rate" />
        <MetricsChart data={metrics} dataKey="policyLoss" color="#ef4444" label="Policy Loss" />
        <MetricsChart data={metrics} dataKey="valueLoss" color="#f97316" label="Value Loss" />
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
                    {['#', 'Bot Level', 'Score', 'Winner', 'Frames', 'Rallies'].map(h => (
                      <th key={h} scope="col">{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {recentGames.slice(0, 20).map((g, i) => (
                    <tr key={g.id}>
                      <td className="text-muted">{i + 1}</td>
                      <td>L{g.botLevel}</td>
                      <td>
                        <span className="score-p1">{g.score1}</span>
                        {' : '}
                        <span className="score-p2">{g.score2}</span>
                      </td>
                      <td className={g.winner === 1 ? 'winner-agent' : 'winner-bot'}>
                        {g.winner === 1 ? 'RL Agent' : 'Bot'}
                      </td>
                      <td className="text-muted">{g.durationFrames}</td>
                      <td className="text-muted">{g.rallyCount}</td>
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
