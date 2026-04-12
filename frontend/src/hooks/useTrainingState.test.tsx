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

function mockFetchStatusOnce(payload: Record<string, unknown>) {
  const fetchMock = vi.fn(async () => ({
    ok: true,
    json: async () => payload,
    text: async () => '',
  } as unknown as Response))
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

// ── Probe component ─────────────────────────────────────

function Probe() {
  const { status, connectionState } = useTrainingState()
  return (
    <div>
      <span data-testid="state">{status.state}</span>
      <span data-testid="step">{status.currentStep}</span>
      <span data-testid="conn">{connectionState}</span>
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

describe('useTrainingState — REST status sync', () => {
  it('fetches /api/training/status on mount and updates state to running', async () => {
    // Backend says training is already running — page refresh scenario.
    const fetchMock = mockFetchStatusOnce({
      state: 'running',
      current_step: 4242,
      current_episode: 17,
    })

    render(
      <TrainingStateProvider>
        <Probe />
      </TrainingStateProvider>,
    )

    // On mount, status defaults to stopped — then the REST probe lands.
    await waitFor(() => {
      expect(screen.getByTestId('state').textContent).toBe('running')
    })
    expect(screen.getByTestId('step').textContent).toBe('4242')
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/training/status',
      expect.objectContaining({ headers: expect.any(Object) }),
    )
  })

  it('refetches /api/training/status when the WebSocket reconnects', async () => {
    // First call: state=stopped (dashboard opened while training was idle)
    // Second call: state=running (after a mid-session reconnect)
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({ state: 'stopped', current_step: 0, current_episode: 0 }),
      })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({ state: 'stopped', current_step: 0, current_episode: 0 }),
      })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({ state: 'running', current_step: 99, current_episode: 3 }),
      })
    vi.stubGlobal('fetch', fetchMock)

    render(
      <TrainingStateProvider>
        <Probe />
      </TrainingStateProvider>,
    )

    // First transition to connected triggers the second call
    await act(async () => {
      MockWebSocket.instances[0]?.simulateOpen()
    })
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2))

    // Drop the connection and reconnect — should fire another fetch
    await act(async () => {
      MockWebSocket.instances[0]?.simulateClose()
    })
    // A new socket is created on reconnect; open it and verify refetch.
    await waitFor(() => expect(MockWebSocket.instances.length).toBeGreaterThan(1))
    await act(async () => {
      MockWebSocket.instances[MockWebSocket.instances.length - 1]?.simulateOpen()
    })

    await waitFor(() => {
      expect(screen.getByTestId('state').textContent).toBe('running')
    })
    expect(fetchMock.mock.calls.length).toBeGreaterThanOrEqual(3)
  })

  it('ignores REST errors silently (WS remains the live channel)', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: false,
      status: 500,
      json: async () => ({}),
      text: async () => 'boom',
    })
    vi.stubGlobal('fetch', fetchMock)

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
