import type { TrainingStatus, ConnectionState, WSClientMessageType } from '../../lib/types'
import './TrainingControls.css'

interface TrainingControlsProps {
  status: TrainingStatus
  connectionState: ConnectionState
  reconnectAttempt?: number
  send: (type: WSClientMessageType, payload?: unknown) => void
  /** Start training with the currently-selected hyperparameters + bot level. */
  onStart: () => void
}

const BOT_LEVELS = [1, 2, 3, 4, 5] as const

export function TrainingControls({
  status,
  connectionState,
  reconnectAttempt = 0,
  send,
  onStart,
}: TrainingControlsProps) {
  const isConnected = connectionState === 'connected'
  const isRunning = status.state === 'running'
  const isStopped = status.state === 'stopped'
  const isPaused = status.state === 'paused'
  const isDisconnected = connectionState === 'disconnected'
  const isConnecting = connectionState === 'connecting'

  const handleStop = () => send('training:stop')
  const handlePause = () => send('training:pause')
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

  // Primary CTA = Start (stopped) or Stop (running/paused). Pause/Resume
  // is a SECONDARY toggle that only appears while training is underway.
  // Do not re-introduce a second Start button inside HyperparamForm or
  // anywhere else — see the duplicate-Start-button regression guard.
  const primaryLabel = isStopped ? 'Start' : 'Stop'
  const primaryAriaLabel = isStopped ? 'Start training' : 'Stop training'
  const primaryVariant = isStopped
    ? 'training-controls-btn--start btn btn-success'
    : 'training-controls-btn--stop btn btn-danger'
  const handlePrimary = () => (isStopped ? onStart() : handleStop())

  const showPauseToggle = isRunning || isPaused
  const pauseLabel = isPaused ? 'Resume' : 'Pause'
  const pauseAriaLabel = isPaused ? 'Resume training' : 'Pause training'
  const pauseVariant = isPaused
    ? 'training-controls-btn--resume btn btn-primary'
    : 'training-controls-btn--pause btn btn-warning'
  const handlePauseToggle = () => (isPaused ? handleResume() : handlePause())

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
        <button
          type="button"
          className={`training-controls-btn ${primaryVariant}`}
          onClick={handlePrimary}
          disabled={!isConnected}
          aria-label={primaryAriaLabel}
          data-training-state={isStopped ? 'stopped' : isRunning ? 'running' : 'paused'}
        >
          {primaryLabel}
        </button>

        {showPauseToggle && (
          <button
            type="button"
            className={`training-controls-btn ${pauseVariant}`}
            onClick={handlePauseToggle}
            disabled={!isConnected}
            aria-label={pauseAriaLabel}
            aria-pressed={isPaused}
            data-pause-state={isPaused ? 'paused' : 'running'}
          >
            {pauseLabel}
          </button>
        )}
      </div>

      <div className="training-controls-level">
        <label className="training-controls-level-label" id="bot-level-label">Bot Level</label>
        <div
          className="training-controls-level-buttons"
          role="group"
          aria-labelledby="bot-level-label"
        >
          {BOT_LEVELS.map(level => {
            const isActive = status.botLevel === level
            return (
              <button
                key={level}
                className={`training-controls-level-btn btn btn-ghost${isActive ? ' active' : ''}`}
                onClick={() => handleSetLevel(level)}
                disabled={!isConnected}
                aria-label={`Set bot level to ${level}`}
                aria-pressed={isActive}
                data-active={isActive}
              >
                L{level}
              </button>
            )
          })}
        </div>
      </div>

      <div className="training-controls-counters" aria-live="polite">
        <span>Step: <strong className="training-controls-counter-value">{status.currentStep.toLocaleString()}</strong></span>
        <span>Episode: <strong className="training-controls-counter-value">{status.currentEpisode.toLocaleString()}</strong></span>
      </div>
    </div>
  )
}
