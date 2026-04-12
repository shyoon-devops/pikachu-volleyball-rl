import type { TrainingStatus, ConnectionState, WSClientMessageType, Hyperparams } from '../../lib/types'
import './TrainingControls.css'

interface TrainingControlsProps {
  status: TrainingStatus
  connectionState: ConnectionState
  reconnectAttempt?: number
  send: (type: WSClientMessageType, payload?: unknown) => void
  onStartWithParams: (params: Hyperparams, botLevel: number) => void
}

const BOT_LEVELS = [1, 2, 3, 4, 5] as const

export function TrainingControls({
  status,
  connectionState,
  reconnectAttempt = 0,
  send,
  onStartWithParams,
}: TrainingControlsProps) {
  const isConnected = connectionState === 'connected'
  const isRunning = status.state === 'running'
  const isStopped = status.state === 'stopped'
  const isDisconnected = connectionState === 'disconnected'
  const isConnecting = connectionState === 'connecting'

  const handleStop = () => send('training:stop')
  const handleResume = () => send('training:resume')
  const handleSetLevel = (level: number) => send('training:set_level', { level })

  const statusState = isConnected ? status.state : 'disconnected'

  const connectionLabel = isConnected
    ? status.state
    : isConnecting
      ? reconnectAttempt > 0
        ? `reconnecting (attempt ${reconnectAttempt})`
        : 'connecting'
      : reconnectAttempt > 0
        ? `disconnected — retry ${reconnectAttempt}`
        : 'disconnected'

  return (
    <div className="training-controls card">
      <div className="training-controls-header">
        <h3 className="training-controls-title" id="training-controls-title">Training Controls</h3>
        <span
          className={`training-controls-status badge badge-${statusState === 'running' ? 'success' : statusState === 'stopped' ? 'danger' : 'warning'}`}
          data-state={statusState}
          role="status"
          aria-live="polite"
          aria-atomic="true"
          aria-label={`Connection: ${connectionLabel}`}
        >
          {connectionLabel}
        </span>
      </div>

      {isDisconnected && reconnectAttempt > 0 && (
        <div className="training-controls-reconnect" role="alert" aria-live="assertive">
          <span className="training-controls-reconnect-icon" aria-hidden="true">⚠</span>
          <span>
            Connection lost. Reconnecting… (attempt {reconnectAttempt})
          </span>
        </div>
      )}

      <div className="training-controls-actions" role="group" aria-labelledby="training-controls-title">
        {isStopped && (
          <button
            className="training-controls-btn training-controls-btn--start btn btn-success"
            onClick={() => onStartWithParams({
              learning_rate: 3e-4,
              n_steps: 2048,
              batch_size: 64,
              gamma: 0.99,
              clip_range: 0.2,
            }, 1)}
            disabled={!isConnected}
            aria-label="Start training"
          >
            Start
          </button>
        )}
        {isRunning && (
          <button
            className="training-controls-btn training-controls-btn--stop btn btn-danger"
            onClick={handleStop}
            disabled={!isConnected}
            aria-label="Stop training"
          >
            Stop
          </button>
        )}
        {status.state === 'paused' && (
          <button
            className="training-controls-btn training-controls-btn--resume btn btn-primary"
            onClick={handleResume}
            disabled={!isConnected}
            aria-label="Resume training"
          >
            Resume
          </button>
        )}
      </div>

      <div className="training-controls-level">
        <label className="training-controls-level-label" id="bot-level-label">Bot Level</label>
        <div className="training-controls-level-buttons" role="group" aria-labelledby="bot-level-label">
          {BOT_LEVELS.map(level => (
            <button
              key={level}
              className="training-controls-level-btn btn btn-ghost"
              onClick={() => handleSetLevel(level)}
              disabled={!isConnected}
              aria-label={`Set bot level to ${level}`}
            >
              L{level}
            </button>
          ))}
        </div>
      </div>

      <div className="training-controls-counters" aria-live="polite">
        <span>Step: <strong className="training-controls-counter-value">{status.currentStep.toLocaleString()}</strong></span>
        <span>Episode: <strong className="training-controls-counter-value">{status.currentEpisode.toLocaleString()}</strong></span>
      </div>
    </div>
  )
}
