import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { renderHook, act } from '@testing-library/react'
import { useWebSocket } from './useWebSocket'

class MockWebSocket {
  static instances: MockWebSocket[] = []

  url: string
  readyState = 0 // CONNECTING
  onopen: ((ev: Event) => void) | null = null
  onclose: ((ev: CloseEvent) => void) | null = null
  onmessage: ((ev: MessageEvent) => void) | null = null
  onerror: ((ev: Event) => void) | null = null

  send = vi.fn()
  close = vi.fn(() => {
    // Simulate the browser firing onclose after close() is called.
    // Tests that need synchronous control over close can set readyState themselves.
  })

  constructor(url: string) {
    this.url = url
    MockWebSocket.instances.push(this)
  }

  simulateOpen() {
    this.readyState = 1 // OPEN
    this.onopen?.(new Event('open'))
  }

  simulateClose() {
    this.readyState = 3 // CLOSED
    this.onclose?.(new CloseEvent('close'))
  }

  simulateMessage(data: unknown) {
    this.onmessage?.(new MessageEvent('message', { data: JSON.stringify(data) }))
  }
}

// Constants to match the internal values
const OPEN = 1

beforeEach(() => {
  MockWebSocket.instances = []
  vi.stubGlobal('WebSocket', MockWebSocket)
  Object.defineProperty(MockWebSocket, 'OPEN', { value: OPEN, configurable: true })
  vi.useFakeTimers()
})

afterEach(() => {
  vi.useRealTimers()
  vi.restoreAllMocks()
})

describe('useWebSocket', () => {
  it('starts in connecting state', () => {
    const { result } = renderHook(() => useWebSocket('ws://localhost:8000/ws'))
    expect(result.current.connectionState).toBe('connecting')
  })

  it('transitions to connected on open', () => {
    const { result } = renderHook(() => useWebSocket('ws://localhost:8000/ws'))

    act(() => {
      MockWebSocket.instances[0]?.simulateOpen()
    })

    expect(result.current.connectionState).toBe('connected')
  })

  it('transitions to disconnected on close', () => {
    const { result } = renderHook(() => useWebSocket('ws://localhost:8000/ws'))

    act(() => {
      MockWebSocket.instances[0]?.simulateOpen()
    })
    expect(result.current.connectionState).toBe('connected')

    act(() => {
      MockWebSocket.instances[0]?.simulateClose()
    })
    expect(result.current.connectionState).toBe('disconnected')
  })

  it('dispatches messages to subscribers', () => {
    const { result } = renderHook(() => useWebSocket('ws://localhost:8000/ws'))
    const handler = vi.fn()

    act(() => {
      MockWebSocket.instances[0]?.simulateOpen()
      result.current.subscribe('training:metrics', handler)
    })

    act(() => {
      MockWebSocket.instances[0]?.simulateMessage({
        type: 'training:metrics',
        payload: { step: 100 },
      })
    })

    expect(handler).toHaveBeenCalledWith({
      type: 'training:metrics',
      payload: { step: 100 },
    })
  })

  it('does not dispatch messages to wrong type subscribers', () => {
    const { result } = renderHook(() => useWebSocket('ws://localhost:8000/ws'))
    const handler = vi.fn()

    act(() => {
      MockWebSocket.instances[0]?.simulateOpen()
      result.current.subscribe('training:frame', handler)
    })

    act(() => {
      MockWebSocket.instances[0]?.simulateMessage({
        type: 'training:metrics',
        payload: { step: 100 },
      })
    })

    expect(handler).not.toHaveBeenCalled()
  })

  it('send calls ws.send with JSON when connected', () => {
    const { result } = renderHook(() => useWebSocket('ws://localhost:8000/ws'))
    const ws = MockWebSocket.instances[0]!

    act(() => {
      ws.simulateOpen()
    })

    act(() => {
      result.current.send('training:start', { bot_level: 1 })
    })

    expect(ws.send).toHaveBeenCalledWith(
      JSON.stringify({ type: 'training:start', payload: { bot_level: 1 } }),
    )
  })

  it('unsubscribe removes handler', () => {
    const { result } = renderHook(() => useWebSocket('ws://localhost:8000/ws'))
    const handler = vi.fn()
    let unsub: () => void = () => {}

    act(() => {
      MockWebSocket.instances[0]?.simulateOpen()
      unsub = result.current.subscribe('training:metrics', handler)
    })

    act(() => {
      unsub()
    })

    act(() => {
      MockWebSocket.instances[0]?.simulateMessage({
        type: 'training:metrics',
        payload: { step: 200 },
      })
    })

    expect(handler).not.toHaveBeenCalled()
  })

  // ── Reconnection (BUG-7 #19) ──
  describe('reconnection', () => {
    it('exposes reconnectAttempt starting at 0', () => {
      const { result } = renderHook(() => useWebSocket('ws://localhost:8000/ws'))
      expect(result.current.reconnectAttempt).toBe(0)
    })

    it('increments reconnectAttempt on close', () => {
      const { result } = renderHook(() => useWebSocket('ws://localhost:8000/ws'))

      act(() => {
        MockWebSocket.instances[0]?.simulateOpen()
      })
      act(() => {
        MockWebSocket.instances[0]?.simulateClose()
      })

      expect(result.current.reconnectAttempt).toBe(1)
      expect(result.current.connectionState).toBe('disconnected')
    })

    it('schedules reconnect with exponential backoff', () => {
      renderHook(() => useWebSocket('ws://localhost:8000/ws'))

      act(() => {
        MockWebSocket.instances[0]?.simulateOpen()
      })
      act(() => {
        MockWebSocket.instances[0]?.simulateClose()
      })

      // Initial reconnect delay is 1s — after 999ms nothing, after 1000ms a new socket
      expect(MockWebSocket.instances).toHaveLength(1)

      act(() => {
        vi.advanceTimersByTime(1000)
      })
      expect(MockWebSocket.instances).toHaveLength(2)
    })

    it('resets reconnect counter to 0 on successful reconnect', () => {
      const { result } = renderHook(() => useWebSocket('ws://localhost:8000/ws'))

      act(() => {
        MockWebSocket.instances[0]?.simulateOpen()
      })
      act(() => {
        MockWebSocket.instances[0]?.simulateClose()
      })
      expect(result.current.reconnectAttempt).toBe(1)

      // Reconnect fires after 1s
      act(() => {
        vi.advanceTimersByTime(1000)
      })

      // New socket opens successfully
      act(() => {
        MockWebSocket.instances[1]?.simulateOpen()
      })

      expect(result.current.connectionState).toBe('connected')
      expect(result.current.reconnectAttempt).toBe(0)
    })

    it('doubles reconnect delay across repeated failures (exponential backoff)', () => {
      renderHook(() => useWebSocket('ws://localhost:8000/ws'))

      // First connect + close → retry after 1s
      act(() => { MockWebSocket.instances[0]?.simulateOpen() })
      act(() => { MockWebSocket.instances[0]?.simulateClose() })

      act(() => { vi.advanceTimersByTime(1000) })
      expect(MockWebSocket.instances).toHaveLength(2)

      // Second failure → retry after 2s
      act(() => { MockWebSocket.instances[1]?.simulateClose() })

      act(() => { vi.advanceTimersByTime(1999) })
      expect(MockWebSocket.instances).toHaveLength(2)

      act(() => { vi.advanceTimersByTime(1) })
      expect(MockWebSocket.instances).toHaveLength(3)
    })

    it('sends heartbeat ping after 30s when connected', () => {
      renderHook(() => useWebSocket('ws://localhost:8000/ws'))
      const ws = MockWebSocket.instances[0]!

      act(() => { ws.simulateOpen() })

      expect(ws.send).not.toHaveBeenCalled()

      act(() => { vi.advanceTimersByTime(30_000) })

      expect(ws.send).toHaveBeenCalledWith(JSON.stringify({ type: 'ping' }))
    })

    it('ignores pong messages (no handler dispatch)', () => {
      const { result } = renderHook(() => useWebSocket('ws://localhost:8000/ws'))
      const handler = vi.fn()

      act(() => {
        MockWebSocket.instances[0]?.simulateOpen()
        result.current.subscribe('pong', handler)
      })

      act(() => {
        MockWebSocket.instances[0]?.simulateMessage({ type: 'pong' })
      })

      expect(handler).not.toHaveBeenCalled()
    })

    it('force-closes socket when pong timeout elapses', () => {
      renderHook(() => useWebSocket('ws://localhost:8000/ws'))
      const ws = MockWebSocket.instances[0]!

      act(() => { ws.simulateOpen() })

      // Trigger ping
      act(() => { vi.advanceTimersByTime(30_000) })
      expect(ws.send).toHaveBeenCalledWith(JSON.stringify({ type: 'ping' }))

      // Pong never arrives — 10s timeout should force close
      act(() => { vi.advanceTimersByTime(10_000) })

      expect(ws.close).toHaveBeenCalled()
    })
  })
})
