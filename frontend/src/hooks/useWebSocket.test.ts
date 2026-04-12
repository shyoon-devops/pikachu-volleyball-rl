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
  close = vi.fn()

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
})

afterEach(() => {
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
    let unsub: () => void

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
})
