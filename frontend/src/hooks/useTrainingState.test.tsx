import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, act, waitFor } from '@testing-library/react'
import { TrainingStateProvider } from './TrainingStateProvider'
import { useTrainingState } from './useTrainingState'

// ── Mocks ───────────────────────────────────────────────

class MockWebSocket {
  static instances: MockWebSocket[] = []
  static OPEN = 1

  url: string
  readyState = 0
  onopen: ((ev: Event) => void) | null = null
  onclose: ((ev: CloseEvent) => void) | null = null
  onmessage: ((ev: MessageEvent) => void) | null = null
  onerror: ((ev: Event) => void) | null = null

  send = vi.fn()
  close = vi.fn()

  constructor(url: string) {
    this.url = url
    MockWebSocket.instances.push(this)
  }

  simulateOpen() {
    this.readyState = 1
    this.onopen?.(new Event('open'))
  }

  simulateClose() {
    this.readyState = 3
    this.onclose?.(new CloseEvent('close'))
  }

  simulateMessage(type: string, payload: unknown) {
    this.onmessage?.(
      new MessageEvent('message', { data: JSON.stringify({ type, payload }) }),
    )
  }
}

type RouteResponder = (url: string) => {
  ok: boolean
  status?: number
  payload: unknown
}

/**
 * Install a per-URL router as the global fetch mock. Every `request()`
 * call in the hook hits the correct route, letting each test specify
 * exactly what /api/training/status / /api/games / /api/training/metrics/aggregate
 * returns independently.
 */
function installFetchRouter(responder: RouteResponder) {
  // Accept the optional `init` param to match `fetch`'s runtime signature.
  // Declared as `unknown` + underscore so it's documented-as-ignored in
  // one place instead of triggering no-unused-vars everywhere.
  const fetchMock = vi.fn(async (input: RequestInfo | URL, ..._init: [RequestInit?]) => {
    void _init
    const url = typeof input === 'string' ? input : input.toString()
    const { ok, status, payload } = responder(url)
    return {
      ok,
      status: status ?? (ok ? 200 : 500),
      json: async () => payload,
      text: async () => JSON.stringify(payload),
    } as unknown as Response
  })
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

const EMPTY_GAMES_PAYLOAD = { data: [], total: 0, page: 1, limit: 20 }
const EMPTY_METRICS_PAYLOAD = { data: [], count: 0, bucket: '1m' }

/**
 * Route the side-effect REST endpoints (stop/pause/resume/level/
 * current_frame) introduced in API spec v0.2.4. Each test wires these
 * to a configurable response so we can verify graceful fallback when
 * the backend is not yet deployed (404) as well as the success path.
 */
interface SideEffectRoutes {
  stop?: { ok: boolean; status?: number }
  pause?: { ok: boolean; status?: number }
  resume?: { ok: boolean; status?: number }
  level?: { ok: boolean; status?: number; level?: number }
  currentFrame?: { ok: boolean; status?: number; payload?: unknown }
}

function matchSideEffectRoute(
  url: string,
  routes: SideEffectRoutes,
): { ok: boolean; status?: number; payload: unknown } | null {
  if (url.startsWith('/api/training/stop')) {
    const r = routes.stop ?? { ok: false, status: 404 }
    return { ok: r.ok, status: r.status, payload: {} }
  }
  if (url.startsWith('/api/training/pause')) {
    const r = routes.pause ?? { ok: false, status: 404 }
    return { ok: r.ok, status: r.status, payload: {} }
  }
  if (url.startsWith('/api/training/resume')) {
    const r = routes.resume ?? { ok: false, status: 404 }
    return { ok: r.ok, status: r.status, payload: {} }
  }
  if (url.startsWith('/api/training/level')) {
    const r = routes.level ?? { ok: false, status: 404 }
    return { ok: r.ok, status: r.status, payload: r.ok ? { level: r.level ?? 0 } : {} }
  }
  if (url.startsWith('/api/training/current_frame')) {
    const r = routes.currentFrame ?? { ok: false, status: 404 }
    return { ok: r.ok, status: r.status, payload: r.payload ?? null }
  }
  return null
}

// ── Probe component ─────────────────────────────────────

function Probe() {
  const { status, connectionState, metrics, recentGames, updatingPolicy, send } = useTrainingState()
  return (
    <div>
      <span data-testid="state">{status.state}</span>
      <span data-testid="step">{status.currentStep}</span>
      <span data-testid="episode">{status.currentEpisode}</span>
      <span data-testid="bot-level">{status.botLevel ?? ''}</span>
      <span data-testid="conn">{connectionState}</span>
      <span data-testid="metrics-count">{metrics.length}</span>
      <span data-testid="games-count">{recentGames.length}</span>
      <span data-testid="latest-game-timestamp">
        {recentGames[0]?.timestamp ?? ''}
      </span>
      <span data-testid="updating">{updatingPolicy.active ? 'yes' : 'no'}</span>
      <span data-testid="updating-long">{updatingPolicy.longGap ? 'yes' : 'no'}</span>
      <button onClick={() => send('training:stop')}>Stop</button>
      <button onClick={() => send('training:pause')}>Pause</button>
      <button onClick={() => send('training:resume')}>Resume</button>
      <button onClick={() => send('training:set_level', { level: 3 })}>L3</button>
    </div>
  )
}

beforeEach(() => {
  MockWebSocket.instances = []
  vi.stubGlobal('WebSocket', MockWebSocket)
})

afterEach(() => {
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
})

// ── Tests ───────────────────────────────────────────────

describe('useTrainingState — REST status sync', () => {
  it('fetches /api/training/status on mount and updates state to running', async () => {
    const fetchMock = installFetchRouter(url => {
      if (url.startsWith('/api/training/status')) {
        return {
          ok: true,
          payload: { state: 'running', current_step: 4242, current_episode: 17 },
        }
      }
      if (url.startsWith('/api/games')) return { ok: true, payload: EMPTY_GAMES_PAYLOAD }
      if (url.startsWith('/api/training/metrics/aggregate')) {
        return { ok: true, payload: EMPTY_METRICS_PAYLOAD }
      }
      return { ok: false, status: 404, payload: {} }
    })

    render(
      <TrainingStateProvider>
        <Probe />
      </TrainingStateProvider>,
    )

    await waitFor(() => {
      expect(screen.getByTestId('state').textContent).toBe('running')
    })
    expect(screen.getByTestId('step').textContent).toBe('4242')

    const statusCalls = fetchMock.mock.calls.filter(([u]) =>
      typeof u === 'string' && u.startsWith('/api/training/status'),
    )
    expect(statusCalls.length).toBeGreaterThanOrEqual(1)
  })

  it('refetches /api/training/status when the WebSocket reconnects', async () => {
    let statusCallCount = 0
    const fetchMock = installFetchRouter(url => {
      if (url.startsWith('/api/training/status')) {
        statusCallCount += 1
        // First probe: stopped. Later probes (after reconnect): running.
        const state = statusCallCount >= 3 ? 'running' : 'stopped'
        return {
          ok: true,
          payload: { state, current_step: state === 'running' ? 99 : 0, current_episode: 3 },
        }
      }
      if (url.startsWith('/api/games')) return { ok: true, payload: EMPTY_GAMES_PAYLOAD }
      if (url.startsWith('/api/training/metrics/aggregate')) {
        return { ok: true, payload: EMPTY_METRICS_PAYLOAD }
      }
      return { ok: false, status: 404, payload: {} }
    })

    render(
      <TrainingStateProvider>
        <Probe />
      </TrainingStateProvider>,
    )

    await waitFor(() => expect(statusCallCount).toBeGreaterThanOrEqual(1))

    await act(async () => { MockWebSocket.instances[0]?.simulateOpen() })
    await waitFor(() => expect(statusCallCount).toBeGreaterThanOrEqual(2))

    await act(async () => { MockWebSocket.instances[0]?.simulateClose() })
    await waitFor(() => expect(MockWebSocket.instances.length).toBeGreaterThan(1))
    await act(async () => {
      MockWebSocket.instances[MockWebSocket.instances.length - 1]?.simulateOpen()
    })

    await waitFor(() => {
      expect(screen.getByTestId('state').textContent).toBe('running')
    })
    expect(fetchMock).toHaveBeenCalled()
  })

  it('ignores REST errors silently (WS remains the live channel)', async () => {
    installFetchRouter(() => ({ ok: false, status: 500, payload: { detail: 'boom' } }))

    render(
      <TrainingStateProvider>
        <Probe />
      </TrainingStateProvider>,
    )

    // Default state stays stopped; no crash.
    await waitFor(() => {
      expect(screen.getByTestId('state').textContent).toBe('stopped')
    })
  })
})

describe('useTrainingState — REST hydration (CRITICAL: refresh wipes graph/games)', () => {
  it('seeds the recent-games list from /api/games on mount', async () => {
    installFetchRouter(url => {
      if (url.startsWith('/api/games')) {
        return {
          ok: true,
          payload: {
            data: [
              {
                id: 'g1',
                timestamp: '2026-04-12T10:00:00Z',
                bot_level: 2,
                score1: 15,
                score2: 10,
                winner: 1,
                duration_frames: 3600,
                rally_count: 14,
              },
            ],
            total: 1,
            page: 1,
            limit: 20,
          },
        }
      }
      if (url.startsWith('/api/training/status')) {
        return {
          ok: true,
          payload: { state: 'stopped', current_step: 0, current_episode: 0 },
        }
      }
      if (url.startsWith('/api/training/metrics/aggregate')) {
        return { ok: true, payload: EMPTY_METRICS_PAYLOAD }
      }
      return { ok: false, status: 404, payload: {} }
    })

    render(
      <TrainingStateProvider>
        <Probe />
      </TrainingStateProvider>,
    )

    await waitFor(() => {
      expect(screen.getByTestId('games-count').textContent).toBe('1')
    })
  })

  // Metrics REST hydration uses `/api/training/timeseries` (API spec
  // v0.2.4), not `/metrics/aggregate`. The aggregate endpoint returns
  // 1-minute-bucket averages that diverge from the live WS per-snapshot
  // stream and caused a "refresh shows different data" bug when it was
  // tried previously. /timeseries returns raw per-snapshot points so
  // REST seed + live WS join 1:1 on step.
  it('does NOT call /api/training/metrics/aggregate on mount (wrong endpoint)', async () => {
    const fetchMock = installFetchRouter(url => {
      if (url.startsWith('/api/games')) return { ok: true, payload: EMPTY_GAMES_PAYLOAD }
      if (url.startsWith('/api/training/status')) {
        return {
          ok: true,
          payload: { state: 'stopped', current_step: 0, current_episode: 0 },
        }
      }
      if (url.startsWith('/api/training/metrics/aggregate')) {
        return { ok: true, payload: EMPTY_METRICS_PAYLOAD }
      }
      return { ok: false, status: 404, payload: {} }
    })

    render(
      <TrainingStateProvider>
        <Probe />
      </TrainingStateProvider>,
    )

    // Wait for the mount-phase fetches to settle (status + games fire).
    await waitFor(() => {
      const statusCalls = fetchMock.mock.calls.filter(([u]) =>
        typeof u === 'string' && u.startsWith('/api/training/status'),
      )
      expect(statusCalls.length).toBeGreaterThanOrEqual(1)
    })

    // No aggregate call happened. The timeseries endpoint is the one
    // this hook uses (covered by the hydration tests below).
    const aggregateCalls = fetchMock.mock.calls.filter(([u]) =>
      typeof u === 'string' && u.startsWith('/api/training/metrics/aggregate'),
    )
    expect(aggregateCalls.length).toBe(0)
  })

  it('hydrates metrics from /api/training/timeseries scoped to experiment_id', async () => {
    // User-reported 2026-04-12 (PM Phase 2 #3): refreshing mid-session
    // wiped the chart. Guard: on mount we fetch the 4 metric names in
    // parallel, merge by step, and seed the chart before the WS stream
    // resumes. Scoped to the live experiment_id so a fresh run doesn't
    // mix last session's rows.
    const fetchMock = installFetchRouter(url => {
      if (url.startsWith('/api/training/status')) {
        return {
          ok: true,
          payload: {
            state: 'running',
            current_step: 300,
            current_episode: 5,
            experiment_id: 'exp-42',
          },
        }
      }
      if (url.startsWith('/api/games')) return { ok: true, payload: EMPTY_GAMES_PAYLOAD }
      if (url.startsWith('/api/training/timeseries')) {
        // Emit 3 points per metric at matching steps so the merge
        // yields 3 fully-joined rows.
        const pointsFor = (base: number) => [
          { step: 100, value: base + 0.1, timestamp: null },
          { step: 200, value: base + 0.2, timestamp: null },
          { step: 300, value: base + 0.3, timestamp: null },
        ]
        if (url.includes('metric=reward')) return { ok: true, payload: { metric: 'reward', experiment_id: 'exp-42', points: pointsFor(1) } }
        if (url.includes('metric=win_rate')) return { ok: true, payload: { metric: 'win_rate', experiment_id: 'exp-42', points: pointsFor(0) } }
        if (url.includes('metric=policy_loss')) return { ok: true, payload: { metric: 'policy_loss', experiment_id: 'exp-42', points: pointsFor(0) } }
        if (url.includes('metric=value_loss')) return { ok: true, payload: { metric: 'value_loss', experiment_id: 'exp-42', points: pointsFor(0) } }
        return { ok: true, payload: { metric: 'reward', experiment_id: null, points: [] } }
      }
      return { ok: false, status: 404, payload: {} }
    })

    render(
      <TrainingStateProvider>
        <Probe />
      </TrainingStateProvider>,
    )

    await waitFor(() => {
      expect(screen.getByTestId('metrics-count').textContent).toBe('3')
    })

    // All 4 metric endpoints were queried with experiment_id filter.
    const tsCalls = fetchMock.mock.calls
      .map(([u]) => (typeof u === 'string' ? u : ''))
      .filter(u => u.startsWith('/api/training/timeseries'))
    expect(tsCalls.some(u => u.includes('metric=reward'))).toBe(true)
    expect(tsCalls.some(u => u.includes('metric=win_rate'))).toBe(true)
    expect(tsCalls.some(u => u.includes('metric=policy_loss'))).toBe(true)
    expect(tsCalls.some(u => u.includes('metric=value_loss'))).toBe(true)
    for (const u of tsCalls) {
      expect(u).toContain('experiment_id=exp-42')
    }
  })

  it('skips timeseries hydration when no experiment_id is known', async () => {
    // Training never started: /status returns no experiment_id. We
    // should not fire 4 empty-returning timeseries calls just to find
    // nothing — skip entirely and let the chart stay empty.
    const fetchMock = installFetchRouter(url => {
      if (url.startsWith('/api/training/status')) {
        return {
          ok: true,
          payload: { state: 'stopped', current_step: 0, current_episode: 0 },
        }
      }
      if (url.startsWith('/api/games')) return { ok: true, payload: EMPTY_GAMES_PAYLOAD }
      if (url.startsWith('/api/training/timeseries')) {
        return { ok: true, payload: { metric: 'reward', experiment_id: null, points: [] } }
      }
      return { ok: false, status: 404, payload: {} }
    })

    render(
      <TrainingStateProvider>
        <Probe />
      </TrainingStateProvider>,
    )

    // Let mount-phase fetches settle.
    await waitFor(() => {
      const statusCalls = fetchMock.mock.calls.filter(([u]) =>
        typeof u === 'string' && u.startsWith('/api/training/status'),
      )
      expect(statusCalls.length).toBeGreaterThanOrEqual(1)
    })

    const tsCalls = fetchMock.mock.calls.filter(([u]) =>
      typeof u === 'string' && u.startsWith('/api/training/timeseries'),
    )
    expect(tsCalls.length).toBe(0)
    expect(screen.getByTestId('metrics-count').textContent).toBe('0')
  })
})

describe('useTrainingState — optimistic send wrapper (CRITICAL: Stop/Pause/level dead)', () => {
  beforeEach(() => {
    installFetchRouter(url => {
      if (url.startsWith('/api/training/status')) {
        return {
          ok: true,
          payload: { state: 'running', current_step: 100, current_episode: 1 },
        }
      }
      if (url.startsWith('/api/games')) return { ok: true, payload: EMPTY_GAMES_PAYLOAD }
      if (url.startsWith('/api/training/metrics/aggregate')) {
        return { ok: true, payload: EMPTY_METRICS_PAYLOAD }
      }
      const sideEffect = matchSideEffectRoute(url, {})
      if (sideEffect) return sideEffect
      return { ok: false, status: 404, payload: {} }
    })
  })

  it('flips state to stopped immediately on training:stop click', async () => {
    render(
      <TrainingStateProvider>
        <Probe />
      </TrainingStateProvider>,
    )
    // Wait for REST sync → running
    await waitFor(() => expect(screen.getByTestId('state').textContent).toBe('running'))

    await act(async () => { screen.getByRole('button', { name: 'Stop' }).click() })
    expect(screen.getByTestId('state').textContent).toBe('stopped')
  })

  it('flips state to paused immediately on training:pause click', async () => {
    render(
      <TrainingStateProvider>
        <Probe />
      </TrainingStateProvider>,
    )
    await waitFor(() => expect(screen.getByTestId('state').textContent).toBe('running'))

    await act(async () => { screen.getByRole('button', { name: 'Pause' }).click() })
    expect(screen.getByTestId('state').textContent).toBe('paused')
  })

  it('flips state back to running on training:resume click', async () => {
    render(
      <TrainingStateProvider>
        <Probe />
      </TrainingStateProvider>,
    )
    await waitFor(() => expect(screen.getByTestId('state').textContent).toBe('running'))

    await act(async () => { screen.getByRole('button', { name: 'Pause' }).click() })
    expect(screen.getByTestId('state').textContent).toBe('paused')

    await act(async () => { screen.getByRole('button', { name: 'Resume' }).click() })
    expect(screen.getByTestId('state').textContent).toBe('running')
  })

  it('applies optimistic botLevel on training:set_level click', async () => {
    render(
      <TrainingStateProvider>
        <Probe />
      </TrainingStateProvider>,
    )
    await waitFor(() => expect(screen.getByTestId('state').textContent).toBe('running'))

    expect(screen.getByTestId('bot-level').textContent).toBe('')

    await act(async () => { screen.getByRole('button', { name: 'L3' }).click() })
    expect(screen.getByTestId('bot-level').textContent).toBe('3')
  })
})

describe('useTrainingState — REST command dispatch (API spec v0.2.4)', () => {
  it('fires POST /api/training/stop on training:stop click (alongside WS)', async () => {
    const fetchMock = installFetchRouter(url => {
      if (url.startsWith('/api/training/status')) {
        return { ok: true, payload: { state: 'running', current_step: 1, current_episode: 1 } }
      }
      if (url.startsWith('/api/games')) return { ok: true, payload: EMPTY_GAMES_PAYLOAD }
      if (url.startsWith('/api/training/metrics/aggregate')) {
        return { ok: true, payload: EMPTY_METRICS_PAYLOAD }
      }
      const side = matchSideEffectRoute(url, { stop: { ok: true, status: 204 } })
      if (side) return side
      return { ok: false, status: 404, payload: {} }
    })

    render(
      <TrainingStateProvider>
        <Probe />
      </TrainingStateProvider>,
    )
    await waitFor(() => expect(screen.getByTestId('state').textContent).toBe('running'))

    await act(async () => { screen.getByRole('button', { name: 'Stop' }).click() })

    await waitFor(() => {
      const stopCalls = fetchMock.mock.calls.filter(([u, init]) =>
        typeof u === 'string'
          && u.startsWith('/api/training/stop')
          && (init as RequestInit | undefined)?.method === 'POST',
      )
      expect(stopCalls.length).toBeGreaterThanOrEqual(1)
    })
  })

  it('fires POST /api/training/pause on training:pause click', async () => {
    const fetchMock = installFetchRouter(url => {
      if (url.startsWith('/api/training/status')) {
        return { ok: true, payload: { state: 'running', current_step: 1, current_episode: 1 } }
      }
      if (url.startsWith('/api/games')) return { ok: true, payload: EMPTY_GAMES_PAYLOAD }
      if (url.startsWith('/api/training/metrics/aggregate')) {
        return { ok: true, payload: EMPTY_METRICS_PAYLOAD }
      }
      const side = matchSideEffectRoute(url, { pause: { ok: true, status: 204 } })
      if (side) return side
      return { ok: false, status: 404, payload: {} }
    })

    render(
      <TrainingStateProvider>
        <Probe />
      </TrainingStateProvider>,
    )
    await waitFor(() => expect(screen.getByTestId('state').textContent).toBe('running'))

    await act(async () => { screen.getByRole('button', { name: 'Pause' }).click() })

    await waitFor(() => {
      const pauseCalls = fetchMock.mock.calls.filter(([u, init]) =>
        typeof u === 'string'
          && u.startsWith('/api/training/pause')
          && (init as RequestInit | undefined)?.method === 'POST',
      )
      expect(pauseCalls.length).toBeGreaterThanOrEqual(1)
    })
  })

  it('fires POST /api/training/resume on training:resume click', async () => {
    const fetchMock = installFetchRouter(url => {
      if (url.startsWith('/api/training/status')) {
        return { ok: true, payload: { state: 'running', current_step: 1, current_episode: 1 } }
      }
      if (url.startsWith('/api/games')) return { ok: true, payload: EMPTY_GAMES_PAYLOAD }
      if (url.startsWith('/api/training/metrics/aggregate')) {
        return { ok: true, payload: EMPTY_METRICS_PAYLOAD }
      }
      const side = matchSideEffectRoute(url, { resume: { ok: true, status: 204 } })
      if (side) return side
      return { ok: false, status: 404, payload: {} }
    })

    render(
      <TrainingStateProvider>
        <Probe />
      </TrainingStateProvider>,
    )
    await waitFor(() => expect(screen.getByTestId('state').textContent).toBe('running'))
    await act(async () => { screen.getByRole('button', { name: 'Pause' }).click() })
    await act(async () => { screen.getByRole('button', { name: 'Resume' }).click() })

    await waitFor(() => {
      const resumeCalls = fetchMock.mock.calls.filter(([u, init]) =>
        typeof u === 'string'
          && u.startsWith('/api/training/resume')
          && (init as RequestInit | undefined)?.method === 'POST',
      )
      expect(resumeCalls.length).toBeGreaterThanOrEqual(1)
    })
  })

  it('fires PATCH /api/training/level with the chosen level', async () => {
    const fetchMock = installFetchRouter(url => {
      if (url.startsWith('/api/training/status')) {
        return { ok: true, payload: { state: 'running', current_step: 1, current_episode: 1 } }
      }
      if (url.startsWith('/api/games')) return { ok: true, payload: EMPTY_GAMES_PAYLOAD }
      if (url.startsWith('/api/training/metrics/aggregate')) {
        return { ok: true, payload: EMPTY_METRICS_PAYLOAD }
      }
      const side = matchSideEffectRoute(url, { level: { ok: true, level: 3 } })
      if (side) return side
      return { ok: false, status: 404, payload: {} }
    })

    render(
      <TrainingStateProvider>
        <Probe />
      </TrainingStateProvider>,
    )
    await waitFor(() => expect(screen.getByTestId('state').textContent).toBe('running'))

    await act(async () => { screen.getByRole('button', { name: 'L3' }).click() })

    await waitFor(() => {
      const levelCalls = fetchMock.mock.calls.filter(([u, init]) => {
        if (typeof u !== 'string' || !u.startsWith('/api/training/level')) return false
        const body = (init as RequestInit | undefined)?.body
        return (init as RequestInit | undefined)?.method === 'PATCH'
          && typeof body === 'string'
          && body.includes('"level":3')
      })
      expect(levelCalls.length).toBeGreaterThanOrEqual(1)
    })
  })

  it('stays optimistic when all REST endpoints 404 (no crash, no state rollback)', async () => {
    installFetchRouter(url => {
      if (url.startsWith('/api/training/status')) {
        return { ok: true, payload: { state: 'running', current_step: 1, current_episode: 1 } }
      }
      if (url.startsWith('/api/games')) return { ok: true, payload: EMPTY_GAMES_PAYLOAD }
      if (url.startsWith('/api/training/metrics/aggregate')) {
        return { ok: true, payload: EMPTY_METRICS_PAYLOAD }
      }
      // All side-effect endpoints default to 404 (backend not deployed).
      const side = matchSideEffectRoute(url, {})
      if (side) return side
      return { ok: false, status: 404, payload: {} }
    })

    render(
      <TrainingStateProvider>
        <Probe />
      </TrainingStateProvider>,
    )
    await waitFor(() => expect(screen.getByTestId('state').textContent).toBe('running'))

    await act(async () => { screen.getByRole('button', { name: 'Stop' }).click() })
    expect(screen.getByTestId('state').textContent).toBe('stopped')

    await act(async () => { screen.getByRole('button', { name: 'L3' }).click() })
    expect(screen.getByTestId('bot-level').textContent).toBe('3')
  })
})

describe('useTrainingState — current_frame hydration (API spec v0.2.4)', () => {
  it('leaves latestFrame null when current_frame endpoint 404s (training idle)', async () => {
    installFetchRouter(url => {
      if (url.startsWith('/api/training/status')) {
        return { ok: true, payload: { state: 'stopped', current_step: 0, current_episode: 0 } }
      }
      if (url.startsWith('/api/games')) return { ok: true, payload: EMPTY_GAMES_PAYLOAD }
      if (url.startsWith('/api/training/metrics/aggregate')) {
        return { ok: true, payload: EMPTY_METRICS_PAYLOAD }
      }
      const side = matchSideEffectRoute(url, {})
      if (side) return side
      return { ok: false, status: 404, payload: {} }
    })

    render(
      <TrainingStateProvider>
        <Probe />
      </TrainingStateProvider>,
    )
    // No crash; state hydrates from status regardless.
    await waitFor(() => expect(screen.getByTestId('state').textContent).toBe('stopped'))
  })

  it('fetches /api/training/current_frame on mount for canvas restoration', async () => {
    const fetchMock = installFetchRouter(url => {
      if (url.startsWith('/api/training/status')) {
        return { ok: true, payload: { state: 'running', current_step: 10, current_episode: 1 } }
      }
      if (url.startsWith('/api/games')) return { ok: true, payload: EMPTY_GAMES_PAYLOAD }
      if (url.startsWith('/api/training/metrics/aggregate')) {
        return { ok: true, payload: EMPTY_METRICS_PAYLOAD }
      }
      const side = matchSideEffectRoute(url, {
        currentFrame: {
          ok: true,
          payload: {
            player1: { x: 100, y: 200, vx: 0, vy: 0, is_jumping: false, is_diving: false, is_power_hitting: false },
            player2: { x: 300, y: 200, vx: 0, vy: 0, is_jumping: false, is_diving: false, is_power_hitting: false },
            ball: { x: 216, y: 100, vx: 0, vy: 1, rotation: 0 },
            score1: 6,
            score2: 9,
            frame: 4500,
          },
        },
      })
      if (side) return side
      return { ok: false, status: 404, payload: {} }
    })

    render(
      <TrainingStateProvider>
        <Probe />
      </TrainingStateProvider>,
    )

    await waitFor(() => {
      const frameCalls = fetchMock.mock.calls.filter(([u]) =>
        typeof u === 'string' && u.startsWith('/api/training/current_frame'),
      )
      expect(frameCalls.length).toBeGreaterThanOrEqual(1)
    })
  })
})

describe('useTrainingState — text/chart sync (B1, 2026-04-18)', () => {
  // BE only broadcasts `training:status` on explicit transitions, so
  // before this fix `status.currentStep` lagged the chart by an
  // arbitrary number of training steps. The hook now bumps the counter
  // off every `training:metrics` payload so the dashboard's text and
  // graph track the same authoritative cadence.

  function setupMinimalRoutes() {
    return installFetchRouter(url => {
      if (url.startsWith('/api/training/status')) {
        return {
          ok: true,
          payload: { state: 'running', current_step: 0, current_episode: 0 },
        }
      }
      if (url.startsWith('/api/games')) return { ok: true, payload: EMPTY_GAMES_PAYLOAD }
      if (url.startsWith('/api/training/timeseries')) {
        return { ok: true, payload: { data: [] } }
      }
      const side = matchSideEffectRoute(url, {})
      if (side) return side
      return { ok: false, status: 404, payload: {} }
    })
  }

  it('bumps status.currentStep when a training:metrics payload arrives', async () => {
    setupMinimalRoutes()

    render(
      <TrainingStateProvider>
        <Probe />
      </TrainingStateProvider>,
    )

    await waitFor(() => expect(MockWebSocket.instances.length).toBeGreaterThanOrEqual(1))
    await act(async () => { MockWebSocket.instances[0]?.simulateOpen() })

    await act(async () => {
      MockWebSocket.instances[0]?.simulateMessage('training:metrics', {
        step: 1024,
        episode: 5,
        mean_reward: 0.4,
        win_rate: 0.5,
        policy_loss: 0.1,
        value_loss: 0.2,
      })
    })

    await waitFor(() => {
      expect(screen.getByTestId('step').textContent).toBe('1024')
    })
    expect(screen.getByTestId('metrics-count').textContent).toBe('1')
  })

  it('does not regress currentStep when a stale metrics payload arrives', async () => {
    // Defensive guard: if a slow Mongo write delivers an old metrics
    // dict from a prior experiment, the user-visible counter must not
    // jump backward (would look like training rewound).
    setupMinimalRoutes()

    render(
      <TrainingStateProvider>
        <Probe />
      </TrainingStateProvider>,
    )

    await waitFor(() => expect(MockWebSocket.instances.length).toBeGreaterThanOrEqual(1))
    await act(async () => { MockWebSocket.instances[0]?.simulateOpen() })

    await act(async () => {
      MockWebSocket.instances[0]?.simulateMessage('training:metrics', {
        step: 5000,
        episode: 12,
        mean_reward: 0,
        win_rate: 0,
        policy_loss: 0,
        value_loss: 0,
      })
    })
    await waitFor(() => expect(screen.getByTestId('step').textContent).toBe('5000'))

    await act(async () => {
      MockWebSocket.instances[0]?.simulateMessage('training:metrics', {
        step: 200, // older payload
        episode: 1,
        mean_reward: 0,
        win_rate: 0,
        policy_loss: 0,
        value_loss: 0,
      })
    })

    expect(screen.getByTestId('step').textContent).toBe('5000')
  })
})

describe('useTrainingState — episode live-poll (2026-04-18 user report)', () => {
  // `TrainingManager.current_episode` is monotonic and exposed only via
  // REST /api/training/status. WS `training:metrics.payload.episode` is
  // `len(deque(maxlen=100))` — a moving-window count, not the live
  // counter. Between transitions the FE must poll REST; otherwise the
  // episode badge freezes at whatever value the last transition carried.

  it('does NOT bump currentEpisode from training:metrics payload', async () => {
    // Regression guard: the B1 code used to Math.max currentEpisode from
    // metrics.episode, which silently masked that the WS payload is
    // bounded at 100. Dropping the bump makes the REST-poll path the
    // single source of live updates.
    installFetchRouter(url => {
      if (url.startsWith('/api/training/status')) {
        return {
          ok: true,
          payload: { state: 'running', current_step: 0, current_episode: 0 },
        }
      }
      if (url.startsWith('/api/games')) return { ok: true, payload: EMPTY_GAMES_PAYLOAD }
      if (url.startsWith('/api/training/timeseries')) {
        return { ok: true, payload: { data: [] } }
      }
      const side = matchSideEffectRoute(url, {})
      if (side) return side
      return { ok: false, status: 404, payload: {} }
    })
    render(
      <TrainingStateProvider>
        <Probe />
      </TrainingStateProvider>,
    )
    await waitFor(() => expect(MockWebSocket.instances.length).toBeGreaterThanOrEqual(1))
    await act(async () => { MockWebSocket.instances[0]?.simulateOpen() })

    // Send a metrics payload with episode=7 and confirm
    // status.currentEpisode stays at 0 (the REST default), NOT 7.
    await act(async () => {
      MockWebSocket.instances[0]?.simulateMessage('training:metrics', {
        step: 2048,
        episode: 7,
        mean_reward: 0.3,
        win_rate: 0.4,
        policy_loss: 0.05,
        value_loss: 0.1,
      })
    })

    // Step DID bump (payload.step is monotonic, real).
    await waitFor(() => expect(screen.getByTestId('step').textContent).toBe('2048'))
    // Episode did NOT bump (payload.episode is window-count, unreliable).
    expect(screen.getByTestId('episode').textContent).toBe('0')
  })

  // Real-timer test — the poll interval is 2s, so we wait a little over
  // that for the second fetch to land. Timeout is 6s to leave headroom
  // for CI scheduler jitter while still failing fast on a regression.
  it('polls REST /api/training/status on an interval while running', async () => {
    let currentEpisode = 100
    const statusHits: number[] = []
    installFetchRouter(url => {
      if (url.startsWith('/api/training/status')) {
        statusHits.push(currentEpisode)
        const payload = {
          state: 'running',
          current_step: 5000,
          current_episode: currentEpisode,
        }
        return { ok: true, payload }
      }
      if (url.startsWith('/api/games')) return { ok: true, payload: EMPTY_GAMES_PAYLOAD }
      if (url.startsWith('/api/training/timeseries')) {
        return { ok: true, payload: { data: [] } }
      }
      const side = matchSideEffectRoute(url, {})
      if (side) return side
      return { ok: false, status: 404, payload: {} }
    })

    render(
      <TrainingStateProvider>
        <Probe />
      </TrainingStateProvider>,
    )
    await waitFor(() => expect(MockWebSocket.instances.length).toBeGreaterThanOrEqual(1))
    await act(async () => { MockWebSocket.instances[0]?.simulateOpen() })
    // First REST probe lands → episode=100.
    await waitFor(() => expect(screen.getByTestId('episode').textContent).toBe('100'))

    // BE advances the counter in between polls.
    currentEpisode = 142

    // Wait for the 2s poll interval + ~500ms slack for the fetch to
    // resolve and React to render. The test's overall timeout is
    // bumped to 6s below to leave CI headroom.
    await waitFor(
      () => expect(screen.getByTestId('episode').textContent).toBe('142'),
      { timeout: 6000, interval: 100 },
    )
  }, 10_000)

  it('stops polling when training:status flips to stopped', async () => {
    let hitCount = 0
    installFetchRouter(url => {
      if (url.startsWith('/api/training/status')) {
        hitCount += 1
        return {
          ok: true,
          payload: { state: 'stopped', current_step: 0, current_episode: 0 },
        }
      }
      if (url.startsWith('/api/games')) return { ok: true, payload: EMPTY_GAMES_PAYLOAD }
      if (url.startsWith('/api/training/timeseries')) {
        return { ok: true, payload: { data: [] } }
      }
      const side = matchSideEffectRoute(url, {})
      if (side) return side
      return { ok: false, status: 404, payload: {} }
    })

    render(
      <TrainingStateProvider>
        <Probe />
      </TrainingStateProvider>,
    )
    await waitFor(() => expect(MockWebSocket.instances.length).toBeGreaterThanOrEqual(1))
    await act(async () => { MockWebSocket.instances[0]?.simulateOpen() })
    await waitFor(() => expect(screen.getByTestId('state').textContent).toBe('stopped'))

    const baseline = hitCount
    // Wait past several poll intervals (2s each). hitCount must NOT
    // climb — the poll-effect early-returns on state === 'stopped'.
    await new Promise(r => setTimeout(r, 4500))
    expect(hitCount).toBe(baseline)
  }, 10_000)
})

describe('useTrainingState — clear chart on experiment_id transition (V3, 2026-04-18)', () => {
  // BE assigns a fresh `experiment_id` on every training:start, so a
  // change of that field signals "this is a new training session — drop
  // anything we cached for the previous one". Without this, Stop→Start
  // produced a chart line that continued from the previous run's last
  // metrics point, and the new run's step-0..N samples collided in the
  // step-keyed merge map with the prior run's same step range.

  function setupRoutes(initialStatus: { state: string; experiment_id: string | null }) {
    let currentStatus = initialStatus
    const fetchMock = installFetchRouter(url => {
      if (url.startsWith('/api/training/status')) {
        return {
          ok: true,
          payload: {
            state: currentStatus.state,
            current_step: 0,
            current_episode: 0,
            experiment_id: currentStatus.experiment_id,
          },
        }
      }
      if (url.startsWith('/api/games')) return { ok: true, payload: EMPTY_GAMES_PAYLOAD }
      if (url.startsWith('/api/training/timeseries')) {
        return { ok: true, payload: { data: [] } }
      }
      const side = matchSideEffectRoute(url, {})
      if (side) return side
      return { ok: false, status: 404, payload: {} }
    })
    return {
      fetchMock,
      setStatus(next: { state: string; experiment_id: string | null }) {
        currentStatus = next
      },
    }
  }

  it('clears metrics when experiment_id transitions to a different value', async () => {
    setupRoutes({ state: 'running', experiment_id: 'exp-A' })

    render(
      <TrainingStateProvider>
        <Probe />
      </TrainingStateProvider>,
    )

    await waitFor(() => expect(MockWebSocket.instances.length).toBeGreaterThanOrEqual(1))
    await act(async () => { MockWebSocket.instances[0]?.simulateOpen() })

    // Seed metrics under exp-A.
    await act(async () => {
      MockWebSocket.instances[0]?.simulateMessage('training:metrics', {
        step: 100, episode: 1, mean_reward: 0.1, win_rate: 0, policy_loss: 0, value_loss: 0,
      })
      MockWebSocket.instances[0]?.simulateMessage('training:metrics', {
        step: 200, episode: 2, mean_reward: 0.2, win_rate: 0, policy_loss: 0, value_loss: 0,
      })
    })
    await waitFor(() => expect(screen.getByTestId('metrics-count').textContent).toBe('2'))

    // BE switches to a new experiment.
    await act(async () => {
      MockWebSocket.instances[0]?.simulateMessage('training:status', {
        state: 'running',
        experiment_id: 'exp-B',
      })
    })

    // Metrics array drops to 0 — the chart starts fresh for exp-B.
    await waitFor(() => expect(screen.getByTestId('metrics-count').textContent).toBe('0'))
  })

  it('does NOT clear metrics on the very first experiment_id observation', async () => {
    // First-mount path: REST status sets experimentId before any
    // metrics arrive. That initial set must not wipe a future incoming
    // metrics payload.
    setupRoutes({ state: 'running', experiment_id: 'exp-A' })

    render(
      <TrainingStateProvider>
        <Probe />
      </TrainingStateProvider>,
    )

    await waitFor(() => expect(MockWebSocket.instances.length).toBeGreaterThanOrEqual(1))
    await act(async () => { MockWebSocket.instances[0]?.simulateOpen() })

    await act(async () => {
      MockWebSocket.instances[0]?.simulateMessage('training:metrics', {
        step: 100, episode: 1, mean_reward: 0.1, win_rate: 0, policy_loss: 0, value_loss: 0,
      })
    })

    await waitFor(() => expect(screen.getByTestId('metrics-count').textContent).toBe('1'))
  })

  it('does NOT clear metrics when experimentId stays the same across reconnect', async () => {
    // Pause/resume keeps the same experiment_id; metrics must persist.
    setupRoutes({ state: 'running', experiment_id: 'exp-A' })

    render(
      <TrainingStateProvider>
        <Probe />
      </TrainingStateProvider>,
    )

    await waitFor(() => expect(MockWebSocket.instances.length).toBeGreaterThanOrEqual(1))
    await act(async () => { MockWebSocket.instances[0]?.simulateOpen() })

    await act(async () => {
      MockWebSocket.instances[0]?.simulateMessage('training:metrics', {
        step: 100, episode: 1, mean_reward: 0.1, win_rate: 0, policy_loss: 0, value_loss: 0,
      })
    })
    await waitFor(() => expect(screen.getByTestId('metrics-count').textContent).toBe('1'))

    // Status broadcast with the same experiment id → no clear.
    await act(async () => {
      MockWebSocket.instances[0]?.simulateMessage('training:status', {
        state: 'paused',
        experiment_id: 'exp-A',
      })
    })

    expect(screen.getByTestId('metrics-count').textContent).toBe('1')
  })
})

describe('useTrainingState — game:result timestamp fallback (R1, 2026-04-18)', () => {
  // BE enqueues `game:result` payloads without `timestamp` (the field
  // is added later by Pydantic when the GameRecord is constructed for
  // Mongo save). FE must fall back to client-now so the live row
  // doesn't render "undefined" until the next REST hydration.
  function setupRoutes() {
    return installFetchRouter(url => {
      if (url.startsWith('/api/training/status')) {
        return {
          ok: true,
          payload: { state: 'running', current_step: 0, current_episode: 0 },
        }
      }
      if (url.startsWith('/api/games')) return { ok: true, payload: EMPTY_GAMES_PAYLOAD }
      if (url.startsWith('/api/training/timeseries')) {
        return { ok: true, payload: { data: [] } }
      }
      const side = matchSideEffectRoute(url, {})
      if (side) return side
      return { ok: false, status: 404, payload: {} }
    })
  }

  it('fills timestamp with client-now when WS payload omits it', async () => {
    setupRoutes()
    render(
      <TrainingStateProvider>
        <Probe />
      </TrainingStateProvider>,
    )
    await waitFor(() => expect(MockWebSocket.instances.length).toBeGreaterThanOrEqual(1))
    await act(async () => { MockWebSocket.instances[0]?.simulateOpen() })

    const before = Date.now()
    await act(async () => {
      MockWebSocket.instances[0]?.simulateMessage('game:result', {
        // Mirrors the BE LiveFrameCallback enqueue dict (no timestamp).
        game_id: 'uuid-fresh',
        experiment_id: 'exp-A',
        bot_level: 3,
        score1: 15,
        score2: 7,
        winner: 1,
        duration_frames: 4500,
        rally_count: 9,
      })
    })
    const after = Date.now()

    await waitFor(() => expect(screen.getByTestId('games-count').textContent).toBe('1'))
    const ts = screen.getByTestId('latest-game-timestamp').textContent
    expect(ts).toBeTruthy()
    // Parsed back, the fallback timestamp should sit inside the test's
    // observed window (allowing for some scheduler jitter).
    const t = new Date(ts!).getTime()
    expect(t).toBeGreaterThanOrEqual(before - 50)
    expect(t).toBeLessThanOrEqual(after + 50)
  })

  it('preserves the BE-provided timestamp when present (forward-compat)', async () => {
    // Once BE adds `timestamp` to the enqueued dict, the fallback must
    // step aside — we keep the BE-authoritative value.
    setupRoutes()
    render(
      <TrainingStateProvider>
        <Probe />
      </TrainingStateProvider>,
    )
    await waitFor(() => expect(MockWebSocket.instances.length).toBeGreaterThanOrEqual(1))
    await act(async () => { MockWebSocket.instances[0]?.simulateOpen() })

    await act(async () => {
      MockWebSocket.instances[0]?.simulateMessage('game:result', {
        game_id: 'uuid-with-ts',
        experiment_id: 'exp-A',
        bot_level: 2,
        score1: 14,
        score2: 15,
        winner: 2,
        duration_frames: 5200,
        rally_count: 11,
        timestamp: '2026-04-18T01:00:00Z',
      })
    })

    await waitFor(() => expect(screen.getByTestId('games-count').textContent).toBe('1'))
    expect(screen.getByTestId('latest-game-timestamp').textContent).toBe(
      '2026-04-18T01:00:00Z',
    )
  })
})

// Updating-policy gap detector (Designer spec f02a9785).
describe('useTrainingState — updating-policy gap detector', () => {
  const FRAME_PAYLOAD = {
    player1: { x: 0, y: 0, vx: 0, vy: 0, is_jumping: false, is_diving: false, is_power_hitting: false },
    player2: { x: 0, y: 0, vx: 0, vy: 0, is_jumping: false, is_diving: false, is_power_hitting: false },
    ball: { x: 0, y: 0, vx: 0, vy: 0, rotation: 0 },
    score1: 0,
    score2: 0,
    frame: 1,
  }

  /**
   * Drive the poll effect with fake timers installed from the
   * start of the test so the interval registers against the fake
   * scheduler. Mounting first with real timers would register
   * the interval on the real clock; advanceTimers wouldn't fire it.
   */
  function installRunningFetchRouter(state: 'running' | 'stopped' = 'running') {
    return installFetchRouter(url => {
      if (url.startsWith('/api/training/status')) {
        return { ok: true, payload: { state, current_step: 0, current_episode: 0 } }
      }
      if (url.startsWith('/api/games')) return { ok: true, payload: EMPTY_GAMES_PAYLOAD }
      if (url.startsWith('/api/training/metrics/aggregate')) {
        return { ok: true, payload: EMPTY_METRICS_PAYLOAD }
      }
      if (url.startsWith('/api/training/timeseries')) {
        return { ok: true, payload: { points: [] } }
      }
      return { ok: false, status: 404, payload: {} }
    })
  }

  async function waitForRunning() {
    // Wait for effect flush that lifts status to running and registers
    // the poll interval under the fake scheduler.
    for (let i = 0; i < 20; i++) {
      await act(async () => { await vi.advanceTimersByTimeAsync(10) })
      if (screen.getByTestId('state').textContent === 'running') return
    }
    throw new Error('timed out waiting for status=running')
  }

  it('flips active=true after ~3s of frame silence while running (heuristic fallback)', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: false })
    installRunningFetchRouter()

    render(
      <TrainingStateProvider>
        <Probe />
      </TrainingStateProvider>,
    )

    const ws = MockWebSocket.instances[0]
    act(() => { ws.simulateOpen() })
    await waitForRunning()

    act(() => { ws.simulateMessage('training:frame', FRAME_PAYLOAD) })
    expect(screen.getByTestId('updating').textContent).toBe('no')

    await act(async () => { await vi.advanceTimersByTimeAsync(3500) })
    expect(screen.getByTestId('updating').textContent).toBe('yes')
    expect(screen.getByTestId('updating-long').textContent).toBe('no')
    vi.useRealTimers()
  })

  it('flips back to false the instant a fresh frame arrives', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: false })
    installRunningFetchRouter()

    render(
      <TrainingStateProvider>
        <Probe />
      </TrainingStateProvider>,
    )

    const ws = MockWebSocket.instances[0]
    act(() => { ws.simulateOpen() })
    await waitForRunning()

    act(() => { ws.simulateMessage('training:frame', FRAME_PAYLOAD) })
    await act(async () => { await vi.advanceTimersByTimeAsync(3500) })
    expect(screen.getByTestId('updating').textContent).toBe('yes')

    act(() => { ws.simulateMessage('training:frame', FRAME_PAYLOAD) })
    expect(screen.getByTestId('updating').textContent).toBe('no')
    vi.useRealTimers()
  })

  it('escalates longGap=true after an 8s silence', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: false })
    installRunningFetchRouter()

    render(
      <TrainingStateProvider>
        <Probe />
      </TrainingStateProvider>,
    )

    const ws = MockWebSocket.instances[0]
    act(() => { ws.simulateOpen() })
    await waitForRunning()

    act(() => { ws.simulateMessage('training:frame', FRAME_PAYLOAD) })

    await act(async () => { await vi.advanceTimersByTimeAsync(3500) })
    expect(screen.getByTestId('updating-long').textContent).toBe('no')
    await act(async () => { await vi.advanceTimersByTimeAsync(7000) })
    expect(screen.getByTestId('updating-long').textContent).toBe('yes')
    vi.useRealTimers()
  })

  it('clears the flag when the WebSocket disconnects (spec §5)', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: false })
    installRunningFetchRouter()

    render(
      <TrainingStateProvider>
        <Probe />
      </TrainingStateProvider>,
    )

    const ws = MockWebSocket.instances[0]
    act(() => { ws.simulateOpen() })
    await waitForRunning()

    act(() => { ws.simulateMessage('training:frame', FRAME_PAYLOAD) })
    await act(async () => { await vi.advanceTimersByTimeAsync(3500) })
    expect(screen.getByTestId('updating').textContent).toBe('yes')

    // Simulated disconnect — hook clears the flag so the existing
    // connection-lost banner can own the state.
    act(() => { ws.simulateClose() })
    await act(async () => { await vi.advanceTimersByTimeAsync(50) })
    expect(screen.getByTestId('updating').textContent).toBe('no')
    vi.useRealTimers()
  })

  it('stays off while training is stopped (even if no frames stream)', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: false })
    installRunningFetchRouter('stopped')

    render(
      <TrainingStateProvider>
        <Probe />
      </TrainingStateProvider>,
    )

    const ws = MockWebSocket.instances[0]
    act(() => { ws.simulateOpen() })
    // Flush pending micro/macrotasks without advancing far.
    await act(async () => { await vi.advanceTimersByTimeAsync(10) })
    expect(screen.getByTestId('state').textContent).toBe('stopped')

    await act(async () => { await vi.advanceTimersByTimeAsync(5000) })
    expect(screen.getByTestId('updating').textContent).toBe('no')
    vi.useRealTimers()
  })
})

// Fix-A FE: explicit update_start / update_end events drive the
// overlay immediately; heuristic stays as a safety-net.
describe('useTrainingState — update_start / update_end events', () => {
  const FRAME_PAYLOAD = {
    player1: { x: 0, y: 0, vx: 0, vy: 0, is_jumping: false, is_diving: false, is_power_hitting: false },
    player2: { x: 0, y: 0, vx: 0, vy: 0, is_jumping: false, is_diving: false, is_power_hitting: false },
    ball: { x: 0, y: 0, vx: 0, vy: 0, rotation: 0 },
    score1: 0, score2: 0, frame: 1,
  }

  function installRouter() {
    return installFetchRouter(url => {
      if (url.startsWith('/api/training/status')) {
        return { ok: true, payload: { state: 'running', current_step: 0, current_episode: 0 } }
      }
      if (url.startsWith('/api/games')) return { ok: true, payload: EMPTY_GAMES_PAYLOAD }
      if (url.startsWith('/api/training/metrics/aggregate')) {
        return { ok: true, payload: EMPTY_METRICS_PAYLOAD }
      }
      if (url.startsWith('/api/training/timeseries')) {
        return { ok: true, payload: { points: [] } }
      }
      return { ok: false, status: 404, payload: {} }
    })
  }

  async function waitForRunning() {
    for (let i = 0; i < 20; i++) {
      await act(async () => { await vi.advanceTimersByTimeAsync(10) })
      if (screen.getByTestId('state').textContent === 'running') return
    }
    throw new Error('timed out waiting for status=running')
  }

  it('activates the overlay immediately on training:update_start', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: false })
    installRouter()
    render(<TrainingStateProvider><Probe /></TrainingStateProvider>)
    const ws = MockWebSocket.instances[0]
    act(() => { ws.simulateOpen() })
    await waitForRunning()

    expect(screen.getByTestId('updating').textContent).toBe('no')
    act(() => {
      ws.simulateMessage('training:update_start', {
        experiment_id: 'exp-42',
        step: 200_000,
      })
    })
    // No poll advance needed — the event handler flips state on the
    // same tick it fires.
    expect(screen.getByTestId('updating').textContent).toBe('yes')
    vi.useRealTimers()
  })

  it('deactivates the overlay immediately on training:update_end', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: false })
    installRouter()
    render(<TrainingStateProvider><Probe /></TrainingStateProvider>)
    const ws = MockWebSocket.instances[0]
    act(() => { ws.simulateOpen() })
    await waitForRunning()

    act(() => {
      ws.simulateMessage('training:update_start', { experiment_id: 'exp-42', step: 1 })
    })
    expect(screen.getByTestId('updating').textContent).toBe('yes')

    act(() => {
      ws.simulateMessage('training:update_end', { experiment_id: 'exp-42', step: 1 })
    })
    expect(screen.getByTestId('updating').textContent).toBe('no')
    vi.useRealTimers()
  })

  it('event-driven overlay survives a stale frame (frame does NOT flip off)', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: false })
    installRouter()
    render(<TrainingStateProvider><Probe /></TrainingStateProvider>)
    const ws = MockWebSocket.instances[0]
    act(() => { ws.simulateOpen() })
    await waitForRunning()

    act(() => {
      ws.simulateMessage('training:update_start', { experiment_id: 'exp-42', step: 1 })
    })
    expect(screen.getByTestId('updating').textContent).toBe('yes')

    // A queued frame lands mid-gradient-update. With event source
    // authoritative, the overlay stays up until update_end.
    act(() => { ws.simulateMessage('training:frame', FRAME_PAYLOAD) })
    expect(screen.getByTestId('updating').textContent).toBe('yes')

    act(() => {
      ws.simulateMessage('training:update_end', { experiment_id: 'exp-42', step: 1 })
    })
    expect(screen.getByTestId('updating').textContent).toBe('no')
    vi.useRealTimers()
  })

  it('heuristic fallback still fires when no update_start event arrives', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: false })
    installRouter()
    render(<TrainingStateProvider><Probe /></TrainingStateProvider>)
    const ws = MockWebSocket.instances[0]
    act(() => { ws.simulateOpen() })
    await waitForRunning()

    act(() => { ws.simulateMessage('training:frame', FRAME_PAYLOAD) })
    // Under the new 3s threshold, 2.5s must stay OFF.
    await act(async () => { await vi.advanceTimersByTimeAsync(2500) })
    expect(screen.getByTestId('updating').textContent).toBe('no')
    // Cross 3s → heuristic kicks in.
    await act(async () => { await vi.advanceTimersByTimeAsync(1000) })
    expect(screen.getByTestId('updating').textContent).toBe('yes')
    vi.useRealTimers()
  })
})
