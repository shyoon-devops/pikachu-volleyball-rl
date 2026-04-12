import { useTrainingState } from '../hooks/useTrainingState'
import './ConnectionIndicator.css'

type IndicatorVariant = 'connected' | 'connecting' | 'reconnecting' | 'disconnected'

interface IndicatorInfo {
  variant: IndicatorVariant
  label: string
  /** Full text for screen readers. */
  ariaLabel: string
}

function pickIndicator(
  connectionState: 'connecting' | 'connected' | 'disconnected',
  reconnectAttempt: number,
): IndicatorInfo {
  if (connectionState === 'connected') {
    return {
      variant: 'connected',
      label: 'Online',
      ariaLabel: 'WebSocket connection: online',
    }
  }
  if (connectionState === 'connecting') {
    if (reconnectAttempt > 0) {
      return {
        variant: 'reconnecting',
        label: `Reconnecting… (#${reconnectAttempt})`,
        ariaLabel: `WebSocket reconnecting, attempt ${reconnectAttempt}`,
      }
    }
    return {
      variant: 'connecting',
      label: 'Connecting…',
      ariaLabel: 'WebSocket connecting',
    }
  }
  // disconnected
  if (reconnectAttempt > 0) {
    return {
      variant: 'reconnecting',
      label: `Offline — retry #${reconnectAttempt}`,
      ariaLabel: `WebSocket offline, retry ${reconnectAttempt}`,
    }
  }
  return {
    variant: 'disconnected',
    label: 'Offline',
    ariaLabel: 'WebSocket offline',
  }
}

/**
 * Global connection state pill shown in the app header. Lives outside
 * the Dashboard so users see reconnect status on every route
 * (History / Replay / Evaluation) — not just while training.
 */
export function ConnectionIndicator() {
  const { connectionState, reconnectAttempt } = useTrainingState()
  const info = pickIndicator(connectionState, reconnectAttempt)

  return (
    <div
      className={`connection-indicator connection-indicator--${info.variant}`}
      role="status"
      aria-live="polite"
      aria-label={info.ariaLabel}
      data-connection-state={connectionState}
      data-reconnect-attempt={reconnectAttempt}
    >
      <span
        className="connection-indicator-dot"
        aria-hidden="true"
      />
      <span className="connection-indicator-label">{info.label}</span>
    </div>
  )
}
