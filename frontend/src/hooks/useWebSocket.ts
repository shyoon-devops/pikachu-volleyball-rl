import { useEffect, useCallback, useState, useSyncExternalStore } from 'react'
import type { ConnectionState, WSMessage, WSMessageType, WSClientMessageType, WSServerMessageType } from '../lib/types'

const MAX_RECONNECT_DELAY = 30_000
const INITIAL_RECONNECT_DELAY = 1_000
const PING_INTERVAL = 30_000
const PONG_TIMEOUT = 10_000

type MessageHandler = (message: WSMessage) => void

/**
 * Topic-narrowing handler signature exposed by the React hook
 * (A6, 2026-04-19). The compiler now sees `msg.type` as the literal
 * topic the caller subscribed to, so downstream zod parsers in
 * `useTrainingState` can branch on `msg.type` exhaustively without
 * casting. Internally the store still keys handlers by topic string.
 */
type NarrowedHandler<T extends WSMessageType> = (message: WSMessage<T>) => void

interface WebSocketSnapshot {
  connectionState: ConnectionState
  reconnectAttempt: number
}

function createWebSocketStore(url: string) {
  let ws: WebSocket | null = null
  let snapshot: WebSocketSnapshot = { connectionState: 'disconnected', reconnectAttempt: 0 }
  let reconnectDelay = INITIAL_RECONNECT_DELAY
  let reconnectTimer: ReturnType<typeof setTimeout> | null = null
  let pingTimer: ReturnType<typeof setInterval> | null = null
  let pongTimer: ReturnType<typeof setTimeout> | null = null
  let destroyed = false
  const listeners = new Set<() => void>()
  const messageHandlers = new Map<string, Set<MessageHandler>>()

  function notify() {
    for (const listener of listeners) {
      listener()
    }
  }

  function setSnapshot(next: Partial<WebSocketSnapshot>) {
    const updated = { ...snapshot, ...next }
    if (updated.connectionState !== snapshot.connectionState || updated.reconnectAttempt !== snapshot.reconnectAttempt) {
      snapshot = updated
      notify()
    }
  }

  function clearReconnectTimer() {
    if (reconnectTimer !== null) {
      clearTimeout(reconnectTimer)
      reconnectTimer = null
    }
  }

  function clearPingTimers() {
    if (pingTimer !== null) {
      clearInterval(pingTimer)
      pingTimer = null
    }
    if (pongTimer !== null) {
      clearTimeout(pongTimer)
      pongTimer = null
    }
  }

  function startPing() {
    clearPingTimers()
    pingTimer = setInterval(() => {
      if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ type: 'ping' }))
        pongTimer = setTimeout(() => {
          // No pong response — force reconnect
          if (ws) {
            ws.close()
          }
        }, PONG_TIMEOUT)
      }
    }, PING_INTERVAL)
  }

  function scheduleReconnect() {
    if (destroyed) return
    clearReconnectTimer()
    const delay = reconnectDelay
    reconnectTimer = setTimeout(() => {
      connect()
    }, delay)
    reconnectDelay = Math.min(delay * 2, MAX_RECONNECT_DELAY)
  }

  function connect() {
    if (destroyed) return
    clearReconnectTimer()
    clearPingTimers()

    if (ws) {
      ws.close()
      ws = null
    }

    setSnapshot({ connectionState: 'connecting', reconnectAttempt: snapshot.reconnectAttempt })
    const socket = new WebSocket(url)

    socket.onopen = () => {
      if (destroyed) {
        socket.close()
        return
      }
      setSnapshot({ connectionState: 'connected', reconnectAttempt: 0 })
      reconnectDelay = INITIAL_RECONNECT_DELAY
      startPing()
    }

    socket.onmessage = (event: MessageEvent) => {
      try {
        const raw = JSON.parse(event.data as string) as { type: string; payload?: unknown }
        // Reset pong timer on any message
        if (pongTimer !== null) {
          clearTimeout(pongTimer)
          pongTimer = null
        }
        if (raw.type === 'pong') return

        const message = raw as WSMessage
        const handlers = messageHandlers.get(raw.type)
        if (handlers) {
          for (const handler of handlers) {
            handler(message)
          }
        }
        const wildcardHandlers = messageHandlers.get('*')
        if (wildcardHandlers) {
          for (const handler of wildcardHandlers) {
            handler(message)
          }
        }
      } catch {
        // Ignore malformed messages
      }
    }

    socket.onclose = () => {
      if (destroyed) return
      clearPingTimers()
      ws = null
      setSnapshot({
        connectionState: 'disconnected',
        reconnectAttempt: snapshot.reconnectAttempt + 1,
      })
      scheduleReconnect()
    }

    socket.onerror = () => {
      // onclose will fire after onerror, triggering reconnect
    }

    ws = socket
  }

  // Reconnect immediately when tab becomes visible
  function handleVisibilityChange() {
    if (document.visibilityState === 'visible' && snapshot.connectionState === 'disconnected') {
      reconnectDelay = INITIAL_RECONNECT_DELAY
      setSnapshot({ reconnectAttempt: 0 })
      connect()
    }
  }

  document.addEventListener('visibilitychange', handleVisibilityChange)

  function destroy() {
    destroyed = true
    document.removeEventListener('visibilitychange', handleVisibilityChange)
    clearReconnectTimer()
    clearPingTimers()
    if (ws) {
      ws.close()
      ws = null
    }
    listeners.clear()
    messageHandlers.clear()
  }

  function send(type: WSClientMessageType, payload?: unknown) {
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ type, payload }))
    }
  }

  function subscribe(callback: () => void) {
    listeners.add(callback)
    return () => { listeners.delete(callback) }
  }

  function getSnapshot(): WebSocketSnapshot {
    return snapshot
  }

  function onMessage(type: string, handler: MessageHandler) {
    if (!messageHandlers.has(type)) {
      messageHandlers.set(type, new Set())
    }
    messageHandlers.get(type)!.add(handler)

    return () => {
      const handlers = messageHandlers.get(type)
      if (handlers) {
        handlers.delete(handler)
        if (handlers.size === 0) {
          messageHandlers.delete(type)
        }
      }
    }
  }

  connect()

  return { subscribe, getSnapshot, send, onMessage, destroy }
}

export function useWebSocket(url: string) {
  const [store] = useState(() => createWebSocketStore(url))

  useEffect(() => {
    return () => {
      store.destroy()
    }
  }, [store])

  const wsSnapshot = useSyncExternalStore(store.subscribe, store.getSnapshot)

  const send = useCallback((type: WSClientMessageType, payload?: unknown) => {
    store.send(type, payload)
  }, [store])

  // Subscribe is generic over the topic so the handler's `msg.type`
  // narrows to the literal subscribed value. The store internals still
  // dispatch via a string key — the narrowing is compiler-only.
  const subscribeMessage = useCallback(
    <T extends WSServerMessageType>(type: T, handler: NarrowedHandler<T>) => {
      return store.onMessage(type, handler as MessageHandler)
    },
    [store],
  )

  return {
    connectionState: wsSnapshot.connectionState,
    reconnectAttempt: wsSnapshot.reconnectAttempt,
    send,
    subscribe: subscribeMessage,
  }
}
