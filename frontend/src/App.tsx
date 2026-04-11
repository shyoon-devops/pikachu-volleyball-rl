import { GameCanvas } from './components/game/GameCanvas'
import { GameOverlay } from './components/game/GameOverlay'
import { useTrainingState } from './hooks/useTrainingState'

function App() {
  const { connectionState, status, latestFrame } = useTrainingState()

  const score1 = latestFrame?.score1 ?? 0
  const score2 = latestFrame?.score2 ?? 0

  const statusText =
    connectionState !== 'connected'
      ? `Connection: ${connectionState}`
      : `Training: ${status.state} | Step ${status.currentStep}`

  return (
    <div style={{ minHeight: '100vh', background: '#0f0f1a', color: '#e0e0e0', fontFamily: 'monospace' }}>
      <header style={{ padding: '16px 24px', borderBottom: '1px solid #2a2a3e' }}>
        <h1 style={{ margin: 0, fontSize: 20, color: '#ffd700' }}>Pikachu Volleyball RL</h1>
      </header>

      <main style={{ padding: 24, display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 16 }}>
        <div style={{ position: 'relative' }}>
          <GameCanvas gameState={latestFrame} width={648} height={456} />
          <GameOverlay score1={score1} score2={score2} statusText={statusText} width={648} />
        </div>

        <div style={{ display: 'flex', gap: 12, fontSize: 13, color: '#888' }}>
          <span>Step: {status.currentStep}</span>
          <span>Episode: {status.currentEpisode}</span>
          <span>State: {status.state}</span>
        </div>
      </main>
    </div>
  )
}

export default App
