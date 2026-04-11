import { GameCanvas } from '../game/GameCanvas'
import { GameOverlay } from '../game/GameOverlay'
import { MetricsChart } from './MetricsChart'
import { TrainingControls } from './TrainingControls'
import { HyperparamForm } from './HyperparamForm'
import { useTrainingState } from '../../hooks/useTrainingState'
import type { Hyperparams } from '../../lib/types'

export function Dashboard() {
  const { connectionState, status, metrics, latestFrame, recentGames, send } = useTrainingState()

  const score1 = latestFrame?.score1 ?? 0
  const score2 = latestFrame?.score2 ?? 0
  const isStopped = status.state === 'stopped'

  const handleStart = (params: Hyperparams, botLevel: number) => {
    send('training:start', { hyperparams: params, bot_level: botLevel })
  }

  return (
    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16, padding: 24, maxWidth: 1400, margin: '0 auto' }}>
      {/* Left column: Controls + Game */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
        <TrainingControls
          status={status}
          connectionState={connectionState}
          send={send}
          onStartWithParams={handleStart}
        />

        <div style={{ position: 'relative' }}>
          <GameCanvas gameState={latestFrame} width={648} height={456} />
          <GameOverlay score1={score1} score2={score2} width={648} />
        </div>

        {isStopped && (
          <HyperparamForm onSubmit={handleStart} disabled={connectionState !== 'connected'} />
        )}
      </div>

      {/* Right column: Charts */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
        <MetricsChart data={metrics} dataKey="reward" color="#22c55e" label="Reward" />
        <MetricsChart data={metrics} dataKey="winRate" color="#3b82f6" label="Win Rate" />
        <MetricsChart data={metrics} dataKey="loss" color="#ef4444" label="Loss" />
      </div>

      {/* Bottom: Recent Games */}
      <div style={{ gridColumn: '1 / -1' }}>
        <div style={{ background: '#1a1a2e', borderRadius: 8, padding: 16, border: '1px solid #2a2a3e' }}>
          <h3 style={{ margin: '0 0 12px', fontSize: 14, color: '#ccc' }}>Recent Games</h3>
          {recentGames.length === 0 ? (
            <p style={{ color: '#666', fontSize: 13, margin: 0 }}>No games yet.</p>
          ) : (
            <div style={{ overflowX: 'auto' }}>
              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
                <thead>
                  <tr style={{ borderBottom: '1px solid #2a2a3e' }}>
                    {['#', 'Bot Level', 'Score', 'Winner', 'Frames', 'Rallies'].map(h => (
                      <th key={h} style={{ textAlign: 'left', padding: '8px 12px', color: '#888', fontWeight: 500 }}>{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {recentGames.slice(0, 20).map((g, i) => (
                    <tr key={g.id} style={{ borderBottom: '1px solid #1f1f30' }}>
                      <td style={{ padding: '6px 12px', color: '#666' }}>{i + 1}</td>
                      <td style={{ padding: '6px 12px' }}>L{g.botLevel}</td>
                      <td style={{ padding: '6px 12px' }}>
                        <span style={{ color: '#ffd700' }}>{g.score1}</span>
                        {' : '}
                        <span style={{ color: '#ff4444' }}>{g.score2}</span>
                      </td>
                      <td style={{ padding: '6px 12px', color: g.winner === 1 ? '#22c55e' : '#ef4444' }}>
                        {g.winner === 1 ? 'RL Agent' : 'Bot'}
                      </td>
                      <td style={{ padding: '6px 12px', color: '#888' }}>{g.durationFrames}</td>
                      <td style={{ padding: '6px 12px', color: '#888' }}>{g.rallyCount}</td>
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
