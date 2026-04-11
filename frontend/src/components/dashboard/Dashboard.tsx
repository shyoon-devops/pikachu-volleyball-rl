import { GameCanvas } from '../game/GameCanvas'
import { GameOverlay } from '../game/GameOverlay'
import { MetricsChart } from './MetricsChart'
import { TrainingControls } from './TrainingControls'
import { HyperparamForm } from './HyperparamForm'
import { useTrainingState } from '../../hooks/useTrainingState'
import type { Hyperparams } from '../../lib/types'
import './Dashboard.css'

export function Dashboard() {
  const { connectionState, status, metrics, latestFrame, recentGames, send } = useTrainingState()

  const score1 = latestFrame?.score1 ?? 0
  const score2 = latestFrame?.score2 ?? 0
  const isStopped = status.state === 'stopped'

  const handleStart = (params: Hyperparams, botLevel: number) => {
    send('training:start', { hyperparams: params, bot_level: botLevel })
  }

  return (
    <div className="dashboard">
      <div className="dashboard-left">
        <TrainingControls
          status={status}
          connectionState={connectionState}
          send={send}
          onStartWithParams={handleStart}
        />

        <div className="dashboard-game-wrapper">
          <GameCanvas gameState={latestFrame} width={648} height={456} />
          <GameOverlay score1={score1} score2={score2} width={648} />
        </div>

        {isStopped && (
          <HyperparamForm onSubmit={handleStart} disabled={connectionState !== 'connected'} />
        )}
      </div>

      <div className="dashboard-right">
        <MetricsChart data={metrics} dataKey="reward" color="#22c55e" label="Reward" />
        <MetricsChart data={metrics} dataKey="winRate" color="#3b82f6" label="Win Rate" />
        <MetricsChart data={metrics} dataKey="loss" color="#ef4444" label="Loss" />
      </div>

      <div className="dashboard-bottom">
        <div className="card">
          <h3 className="card-title">Recent Games</h3>
          {recentGames.length === 0 ? (
            <p className="recent-games-empty">No games yet.</p>
          ) : (
            <div className="recent-games">
              <table className="recent-games-table">
                <thead>
                  <tr>
                    {['#', 'Bot Level', 'Score', 'Winner', 'Frames', 'Rallies'].map(h => (
                      <th key={h}>{h}</th>
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
      </div>
    </div>
  )
}
