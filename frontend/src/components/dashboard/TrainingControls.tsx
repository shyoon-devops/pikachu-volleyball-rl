import type { TrainingStatus, ConnectionState, WSClientMessageType, Hyperparams } from '../../lib/types'
import './TrainingControls.css'

interface TrainingControlsProps {
  status: TrainingStatus
  connectionState: ConnectionState
  send: (type: WSClientMessageType, payload?: unknown) => void
  onStartWithParams: (params: Hyperparams, botLevel: number) => void
}

const BOT_LEVELS = [1, 2, 3, 4, 5] as const

function getStatusBadge(connectionState: ConnectionState, status: TrainingStatus) {
  if (connectionState !== 'connected') {
    return { className: 'badge badge-danger', label: connectionState }
  }
  switch (status.state) {
    case 'running':
      return { className: 'badge badge-success', label: 'running' }
    case 'paused':
      return { className: 'badge badge-warning', label: 'paused' }
    case 'stopped':
      return { className: 'badge badge-danger', label: 'stopped' }
  }
}

export function TrainingControls({ status, connectionState, send, onStartWithParams }: TrainingControlsProps) {
  const isConnected = connectionState === 'connected'
  const isRunning = status.state === 'running'
  const isStopped = status.state === 'stopped'

  const handleStop = () => send('training:stop')
  const handleResume = () => send('training:resume')
  const handleSetLevel = (level: number) => send('training:set_level', { level })

  const badge = getStatusBadge(connectionState, status)

  return (
    <div className="training-controls">
      <div className="training-controls__header">
        <h3 className="training-controls__title">Training Controls</h3>
        <span className={badge.className}>{badge.label}</span>
      </div>

      <div className="training-controls__actions">
        {isStopped && (
          <button
            className="btn btn-success"
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
            className="btn btn-danger"
            onClick={handleStop}
            disabled={!isConnected}
          >
            Stop
          </button>
        )}
        {status.state === 'paused' && (
          <button
            className="btn btn-primary"
            onClick={handleResume}
            disabled={!isConnected}
          >
            Resume
          </button>
        )}
      </div>

      <div className="training-controls__bot-level">
        <label className="training-controls__bot-label">Bot Level</label>
        <div className="training-controls__levels">
          {BOT_LEVELS.map(level => (
            <button
              key={level}
              className="btn btn-ghost"
              onClick={() => handleSetLevel(level)}
              disabled={!isConnected}
            >
              L{level}
            </button>
          ))}
        </div>
      </div>

      <div className="training-controls__stats">
        <span>Step: <strong>{status.currentStep.toLocaleString()}</strong></span>
        <span>Episode: <strong>{status.currentEpisode.toLocaleString()}</strong></span>
      </div>
    </div>
  )
}
