import type { TrainingStatus, ConnectionState, WSClientMessageType, Hyperparams } from '../../lib/types'

interface TrainingControlsProps {
  status: TrainingStatus
  connectionState: ConnectionState
  send: (type: WSClientMessageType, payload?: unknown) => void
  onStartWithParams: (params: Hyperparams, botLevel: number) => void
}

const BOT_LEVELS = [1, 2, 3, 4, 5] as const

const buttonBase: React.CSSProperties = {
  padding: '8px 16px',
  border: 'none',
  borderRadius: 6,
  fontFamily: 'monospace',
  fontSize: 13,
  fontWeight: 600,
  cursor: 'pointer',
  transition: 'opacity 0.15s',
}

export function TrainingControls({ status, connectionState, send, onStartWithParams }: TrainingControlsProps) {
  const isConnected = connectionState === 'connected'
  const isRunning = status.state === 'running'
  const isStopped = status.state === 'stopped'

  const handleStop = () => send('training:stop')
  const handleResume = () => send('training:resume')
  const handleSetLevel = (level: number) => send('training:set_level', { level })

  return (
    <div style={{ background: '#1a1a2e', borderRadius: 8, padding: 16, border: '1px solid #2a2a3e' }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 12 }}>
        <h3 style={{ margin: 0, fontSize: 14, color: '#ccc' }}>Training Controls</h3>
        <span style={{
          fontSize: 11,
          padding: '2px 8px',
          borderRadius: 10,
          background: isConnected
            ? isRunning ? '#1a3a1a' : '#3a3a1a'
            : '#3a1a1a',
          color: isConnected
            ? isRunning ? '#4ade80' : '#fbbf24'
            : '#f87171',
        }}>
          {isConnected ? status.state : connectionState}
        </span>
      </div>

      <div style={{ display: 'flex', gap: 8, marginBottom: 12 }}>
        {isStopped && (
          <button
            style={{ ...buttonBase, background: '#22c55e', color: '#000' }}
            onClick={() => onStartWithParams({
              learning_rate: 3e-4,
              n_steps: 2048,
              batch_size: 64,
              gamma: 0.99,
              clip_range: 0.2,
            }, 1)}
            disabled={!isConnected}
          >
            Start
          </button>
        )}
        {isRunning && (
          <button
            style={{ ...buttonBase, background: '#ef4444', color: '#fff' }}
            onClick={handleStop}
            disabled={!isConnected}
          >
            Stop
          </button>
        )}
        {status.state === 'paused' && (
          <button
            style={{ ...buttonBase, background: '#3b82f6', color: '#fff' }}
            onClick={handleResume}
            disabled={!isConnected}
          >
            Resume
          </button>
        )}
      </div>

      <div style={{ marginBottom: 12 }}>
        <label style={{ fontSize: 12, color: '#888', display: 'block', marginBottom: 4 }}>Bot Level</label>
        <div style={{ display: 'flex', gap: 4 }}>
          {BOT_LEVELS.map(level => (
            <button
              key={level}
              style={{
                ...buttonBase,
                padding: '4px 12px',
                background: '#2a2a3e',
                color: '#ccc',
                fontSize: 12,
              }}
              onClick={() => handleSetLevel(level)}
              disabled={!isConnected}
            >
              L{level}
            </button>
          ))}
        </div>
      </div>

      <div style={{ display: 'flex', gap: 16, fontSize: 12, color: '#888' }}>
        <span>Step: <strong style={{ color: '#e0e0e0' }}>{status.currentStep.toLocaleString()}</strong></span>
        <span>Episode: <strong style={{ color: '#e0e0e0' }}>{status.currentEpisode.toLocaleString()}</strong></span>
      </div>
    </div>
  )
}
