import type { TrainingStatus, ConnectionState, WSClientMessageType, Hyperparams } from '../../lib/types'
import './TrainingControls.css'

interface TrainingControlsProps {
  status: TrainingStatus
  connectionState: ConnectionState
  send: (type: WSClientMessageType, payload?: unknown) => void
  onStartWithParams: (params: Hyperparams, botLevel: number) => void
}

const BOT_LEVELS = [1, 2, 3, 4, 5] as const

export function TrainingControls({ status, connectionState, send, onStartWithParams }: TrainingControlsProps) {
  const isConnected = connectionState === 'connected'
  const isRunning = status.state === 'running'
  const isStopped = status.state === 'stopped'

  const handleStop = () => send('training:stop')
  const handleResume = () => send('training:resume')
  const handleSetLevel = (level: number) => send('training:set_level', { level })

  const statusState = isConnected ? status.state : 'disconnected'

  return (
    <div className="training-controls card">
      <div className="training-controls-header">
        <h3 className="training-controls-title">Training Controls</h3>
        <span className="training-controls-status" data-state={statusState}>
          {isConnected ? status.state : connectionState}
        </span>
      </div>

      <div className="training-controls-actions">
        {isStopped && (
          <button
            className="training-controls-btn training-controls-btn--start"
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
            className="training-controls-btn training-controls-btn--stop"
            onClick={handleStop}
            disabled={!isConnected}
          >
            Stop
          </button>
        )}
        {status.state === 'paused' && (
          <button
            className="training-controls-btn training-controls-btn--resume"
            onClick={handleResume}
            disabled={!isConnected}
          >
            Resume
          </button>
        )}
      </div>

      <div className="training-controls-level">
        <label className="training-controls-level-label">Bot Level</label>
        <div className="training-controls-level-buttons">
          {BOT_LEVELS.map(level => (
            <button
              key={level}
              className="training-controls-level-btn"
              onClick={() => handleSetLevel(level)}
              disabled={!isConnected}
            >
              L{level}
            </button>
          ))}
        </div>
      </div>

      <div className="training-controls-counters">
        <span>Step: <strong className="training-controls-counter-value">{status.currentStep.toLocaleString()}</strong></span>
        <span>Episode: <strong className="training-controls-counter-value">{status.currentEpisode.toLocaleString()}</strong></span>
      </div>
    </div>
  )
}
