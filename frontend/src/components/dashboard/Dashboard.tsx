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
      <div className="dashboard__left">
        <TrainingControls
          status={status}
          connectionState={connectionState}
          send={send}
          onStartWithParams={handleStart}
        />

        <div className="dashboard__game-wrapper">
          <GameCanvas gameState={latestFrame} width={648} height={456} />
          <GameOverlay score1={score1} score2={score2} width={648} />
        </div>

        {isStopped && (
          <HyperparamForm onSubmit={handleStart} disabled={connectionState !== 'connected'} />
        )}
      </div>

      <div className="dashboard__right">
        <MetricsChart data={metrics} dataKey="reward" color="var(--color-chart-green)" label="Reward" />
        <MetricsChart data={metrics} dataKey="winRate" color="var(--color-chart-blue)" label="Win Rate" />
        <MetricsChart data={metrics} dataKey="loss" color="var(--color-chart-red)" label="Loss" />
      </div>

      <div className="dashboard__recent-games">
        <div className="recent-games-card">
          <h3>Recent Games</h3>
          {recentGames.length === 0 ? (
            <div className="empty-state">
              <div className="empty-state-icon">&#9917;</div>
              <span>No games played yet. Start training to see results.</span>
            </div>
          ) : (
            <div style={{ overflowX: 'auto' }}>
              <table>
                <thead>
                  <tr>
                    <th>#</th>
                    <th>Bot Level</th>
                    <th>Score</th>
                    <th>Winner</th>
                    <th>Frames</th>
                    <th>Rallies</th>
                  </tr>
                </thead>
                <tbody>
                  {recentGames.slice(0, 20).map((g, i) => (
                    <tr key={g.id}>
                      <td className="muted">{i + 1}</td>
                      <td>L{g.botLevel}</td>
                      <td>
                        <span className="score-p1">{g.score1}</span>
                        {' : '}
                        <span className="score-p2">{g.score2}</span>
                      </td>
                      <td className={g.winner === 1 ? 'winner-agent' : 'winner-bot'}>
                        {g.winner === 1 ? 'RL Agent' : 'Bot'}
                      </td>
                      <td className="muted">{g.durationFrames}</td>
                      <td className="muted">{g.rallyCount}</td>
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
