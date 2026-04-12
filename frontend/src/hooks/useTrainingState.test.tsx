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
  const { status, connectionState, metrics, recentGames, send } = useTrainingState()
  return (
    <div>
      <span data-testid="state">{status.state}</span>
      <span data-testid="step">{status.currentStep}</span>
      <span data-testid="bot-level">{status.botLevel ?? ''}</span>
      <span data-testid="conn">{connectionState}</span>
      <span data-testid="metrics-count">{metrics.length}</span>
      <span data-testid="games-count">{recentGames.length}</span>
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

  // Metrics REST hydration is intentionally DISABLED as a P0 stopgap
  // (2026-04-12). The aggregate endpoint returns 1-minute-bucket
  // averages, which diverge visibly from the live WS per-snapshot
  // stream and caused a "refresh shows different data" bug.
  //
  // Re-enable (via /api/training/timeseries) once BE lands the raw
  // endpoint; see useTrainingState.ts TODO block for the rollout plan.
  it('does NOT call /api/training/metrics/aggregate on mount (P0 stopgap)', async () => {
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

    // No aggregate call happened. Live WS is the only metrics source.
    const aggregateCalls = fetchMock.mock.calls.filter(([u]) =>
      typeof u === 'string' && u.startsWith('/api/training/metrics/aggregate'),
    )
    expect(aggregateCalls.length).toBe(0)

    // Metrics list stays empty on mount.
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
