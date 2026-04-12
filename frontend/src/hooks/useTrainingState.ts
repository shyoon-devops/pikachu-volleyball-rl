import { createContext, useContext, useState, useEffect, useCallback } from 'react'
import { useWebSocket } from './useWebSocket'
import { snakeToCamel } from '../lib/api'
import type {
  GameState,
  TrainingMetrics,
  TrainingStatus,
  GameRecord,
  ConnectionState,
  WSClientMessageType,
  WSMessage,
} from '../lib/types'

const MAX_METRICS_POINTS = 1000
const MAX_RECENT_GAMES = 100

export interface TrainingState {
  connectionState: ConnectionState
  reconnectAttempt: number
  status: TrainingStatus
  metrics: TrainingMetrics[]
  latestFrame: GameState | null
  recentGames: GameRecord[]
  send: (type: WSClientMessageType, payload?: unknown) => void
}

function getWsUrl(): string {
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  return `${protocol}//${window.location.host}/ws`
}

/**
 * Internal: subscribes to the WebSocket and derives training state.
 * Exported for use by TrainingStateProvider only — every call opens a
 * new socket, so app code should never call this directly. Read via
 * `useTrainingState()` which consumes the shared context instead.
 */
export function useTrainingStateImpl(): TrainingState {
  const { connectionState, reconnectAttempt, send, subscribe } = useWebSocket(getWsUrl())

  const [status, setStatus] = useState<TrainingStatus>({
    state: 'stopped',
    currentStep: 0,
    currentEpisode: 0,
  })
  const [metrics, setMetrics] = useState<TrainingMetrics[]>([])
  const [latestFrame, setLatestFrame] = useState<GameState | null>(null)
  const [recentGames, setRecentGames] = useState<GameRecord[]>([])

  const handleMetrics = useCallback((msg: WSMessage) => {
    const payload = snakeToCamel<TrainingMetrics>(msg.payload)
    setMetrics(prev => {
      const next = [...prev, payload]
      return next.length > MAX_METRICS_POINTS ? next.slice(-MAX_METRICS_POINTS) : next
    })
  }, [])

  const handleFrame = useCallback((msg: WSMessage) => {
    setLatestFrame(snakeToCamel<GameState>(msg.payload))
  }, [])

  const handleStatus = useCallback((msg: WSMessage) => {
    const incoming = snakeToCamel<Partial<TrainingStatus>>(msg.payload)
    setStatus(prev => ({
      ...prev,
      ...incoming,
      state: incoming.state ?? prev.state,
    }))
  }, [])

  const handleGameResult = useCallback((msg: WSMessage) => {
    const record = snakeToCamel<GameRecord>(msg.payload)
    setRecentGames(prev => {
      const next = [record, ...prev]
      return next.length > MAX_RECENT_GAMES ? next.slice(0, MAX_RECENT_GAMES) : next
    })
  }, [])

  useEffect(() => {
    const unsubs = [
      subscribe('training:metrics', handleMetrics),
      subscribe('training:frame', handleFrame),
      subscribe('training:status', handleStatus),
      subscribe('game:result', handleGameResult),
    ]
    return () => { unsubs.forEach(u => u()) }
  }, [subscribe, handleMetrics, handleFrame, handleStatus, handleGameResult])

  return { connectionState, reconnectAttempt, status, metrics, latestFrame, recentGames, send }
}

export const TrainingStateContext = createContext<TrainingState | null>(null)

/**
 * Access the shared training state.
 *
 * Must be rendered under <TrainingStateProvider /> (normal runtime) so
 * every consumer reads from the one WebSocket. Component tests that
 * exercise a consumer in isolation should use `vi.mock` on this module,
 * matching the pattern in Dashboard.test.tsx.
 */
export function useTrainingState(): TrainingState {
  const ctx = useContext(TrainingStateContext)
  if (!ctx) {
    throw new Error(
      'useTrainingState must be used within <TrainingStateProvider />',
    )
  }
  return ctx
}
