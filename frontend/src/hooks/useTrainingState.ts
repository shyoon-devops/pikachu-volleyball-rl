import { createContext, useContext, useState, useEffect, useCallback, useRef } from 'react'
import { useWebSocket } from './useWebSocket'
import {
  snakeToCamel,
  getTrainingStatus,
  getRecentGames,
  getCurrentFrame,
  getTimeseries,
  stopTraining,
  pauseTraining,
  resumeTraining,
  patchTrainingLevel,
} from '../lib/api'
import { mergeTimeseries } from '../lib/mergeTimeseries'
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
/**
 * How many completed games to pull on mount/reconnect. The hook
 * ring-buffer still caps at MAX_RECENT_GAMES; this is just how much
 * history we try to seed so the "Recent Games" panel isn't empty after
 * a refresh. Matches what the dashboard actually renders.
 */
const SEED_RECENT_GAMES = 20

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
  const { connectionState, reconnectAttempt, send: wsSend, subscribe } = useWebSocket(getWsUrl())

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

  // Sync authoritative training state from REST on mount and again whenever
  // the WebSocket reconnects. WS broadcasts `training:status` only when the
  // state *changes*, so a page refresh or mid-session reconnect could leave
  // the UI showing the default 'stopped' state while training is actually
  // running — reported as the refresh-shows-Start / Stop-not-wired bug.
  useEffect(() => {
    if (connectionState !== 'connected') return
    let cancelled = false
    getTrainingStatus()
      .then(fresh => {
        if (cancelled) return
        setStatus(prev => ({ ...prev, ...fresh }))
      })
      .catch(() => {
        // REST probe is best-effort; WS remains the live channel.
      })
    return () => { cancelled = true }
  }, [connectionState])

  // First-mount REST probe, even before the WebSocket opens, so the header
  // and primary CTA are correct on refresh regardless of WS timing.
  useEffect(() => {
    let cancelled = false
    getTrainingStatus()
      .then(fresh => {
        if (cancelled) return
        setStatus(prev => ({ ...prev, ...fresh }))
      })
      .catch(() => { /* best-effort */ })
    return () => { cancelled = true }
  }, [])

  // Seed recent-games table + game canvas from REST on mount. WS streams
  // the live data going forward, but a refresh used to wipe both panels
  // since we started from empty state. REST gives us the current
  // snapshot; the running WS then appends new points on top.
  //
  // `/api/training/current_frame` (API spec v0.2.4) lets the game canvas
  // repaint immediately after refresh instead of waiting ~30ms for the
  // first WS `training:frame`. Returns null when training isn't running —
  // in that case we leave latestFrame null and the canvas renders its
  // idle placeholder.
  useEffect(() => {
    let cancelled = false
    getRecentGames(SEED_RECENT_GAMES)
      .then(games => {
        if (cancelled || games.length === 0) return
        setRecentGames(prev => (prev.length > 0 ? prev : games))
      })
      .catch(() => { /* best-effort */ })
    getCurrentFrame()
      .then(frame => {
        if (cancelled || frame === null) return
        // Only seed if we don't already have a live frame from the WS.
        setLatestFrame(prev => prev ?? frame)
      })
      .catch(() => { /* best-effort */ })
    return () => { cancelled = true }
  }, [])

  // Metrics hydration from `/api/training/timeseries` (API spec v0.2.4).
  //
  // Problem this fixes (user-reported 2026-04-12, PM Phase 2 #3): a page
  // refresh mid-session started the chart empty and only picked up from
  // the next WS `training:metrics` tick onward — the prior thousands of
  // steps were invisible until the user waited out a full log_interval
  // cycle. The previous stopgap disabled hydration entirely because
  // `/api/training/metrics/aggregate` returns wall-clock-bucketed
  // averages that don't line up with the live WS's per-snapshot stream
  // (caused "same step, different Y" on refresh).
  //
  // /timeseries returns the same raw snapshots the WS carries, so REST
  // seed + live stream join 1:1 on `step`. The 4 per-metric calls run
  // in parallel, each .catch()-ing into [] so a failed endpoint
  // degrades one chart line instead of blocking the others.
  //
  // Scoped to `status.experimentId` so a refresh mid-session doesn't
  // mix last run's (step, value) pairs onto this run's chart — training
  // steps reset on each run, so without this filter a fresh experiment
  // starting at step 0 would overlap the previous experiment's step 0
  // rows. The ref gate ensures we hydrate exactly once per
  // experiment_id (not every render that observes the status prop).
  //
  // Live WS wins on merge conflicts: any WS frame that arrived between
  // mount and hydration completion overwrites the REST row for that
  // step, so a brief network delay can't regress the chart.
  const hydratedExpIdRef = useRef<string | null>(null)
  useEffect(() => {
    const expId = status.experimentId
    if (!expId) return
    if (hydratedExpIdRef.current === expId) return
    hydratedExpIdRef.current = expId

    let cancelled = false
    Promise.all([
      getTimeseries('reward', 1000, expId).catch(() => []),
      getTimeseries('win_rate', 1000, expId).catch(() => []),
      getTimeseries('policy_loss', 1000, expId).catch(() => []),
      getTimeseries('value_loss', 1000, expId).catch(() => []),
    ])
      .then(([reward, winRate, policyLoss, valueLoss]) => {
        if (cancelled) return
        const history = mergeTimeseries(reward, winRate, policyLoss, valueLoss)
        if (history.length === 0) return
        setMetrics(prev => {
          const byStep = new Map<number, TrainingMetrics>()
          for (const m of history) byStep.set(m.step, m)
          for (const m of prev) byStep.set(m.step, m) // live wins
          return [...byStep.values()]
            .sort((a, b) => a.step - b.step)
            .slice(-MAX_METRICS_POINTS)
        })
      })
      .catch(() => { /* best-effort — live WS remains authoritative */ })
    return () => { cancelled = true }
  }, [status.experimentId])

  // Wrap the raw WS send so the UI reflects the user's intent the instant
  // they click. Backend's echoed `training:status` broadcast will override
  // this optimistic value when it disagrees. This fixes the reported
  // "Stop/Pause/level buttons don't do anything" symptom — previously we
  // fire-and-forgot the WS message and relied entirely on the return echo
  // that occasionally raced the UI or (for `training:pause`, which the
  // backend does not yet handle over WS) never arrived at all.
  //
  // Dual-channel dispatch (API spec v0.2.4): we fire both the REST
  // command and the WS message. Backend is rolling out REST handlers
  // (POST /api/training/stop|pause|resume, PATCH /api/training/level)
  // alongside the existing WS handlers. Either path landing is
  // sufficient to execute the command; each is idempotent on the
  // backend state. REST failures (404 before deploy, 5xx) are silent —
  // the WS path plus the optimistic UI keep the user in sync.
  //
  // Note for reviewers: once BE confirms REST coverage everywhere, we
  // can drop the WS fallback. Keeping both until then per PM
  // instruction — see docs/NOTICE-FRONTEND-BUTTON-SYNC.md.
  const send = useCallback((type: WSClientMessageType, payload?: unknown) => {
    wsSend(type, payload)
    switch (type) {
      case 'training:start':
        setStatus(prev => ({ ...prev, state: 'running' }))
        break
      case 'training:stop':
        setStatus(prev => ({ ...prev, state: 'stopped' }))
        stopTraining().catch(() => { /* REST not deployed → WS fallback */ })
        break
      case 'training:pause':
        setStatus(prev => ({ ...prev, state: 'paused' }))
        pauseTraining().catch(() => { /* REST not deployed → WS fallback */ })
        break
      case 'training:resume':
        setStatus(prev => ({ ...prev, state: 'running' }))
        resumeTraining().catch(() => { /* REST not deployed → WS fallback */ })
        break
      case 'training:set_level': {
        const level = (payload as { level?: unknown } | undefined)?.level
        if (typeof level === 'number') {
          setStatus(prev => ({ ...prev, botLevel: level }))
          patchTrainingLevel(level).catch(() => { /* REST not deployed → WS fallback */ })
        }
        break
      }
      default:
        // replay:request et al carry no optimistic state.
        break
    }
  }, [wsSend])

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
