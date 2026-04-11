import { useEffect, useCallback, useState, useSyncExternalStore } from 'react'
import type { ConnectionState, WSMessage, WSClientMessageType } from '../lib/types'

const MAX_RECONNECT_DELAY = 30_000
const INITIAL_RECONNECT_DELAY = 1_000

type MessageHandler = (message: WSMessage) => void

function createWebSocketStore(url: string) {
  let ws: WebSocket | null = null
  let state: ConnectionState = 'disconnected'
  let reconnectDelay = INITIAL_RECONNECT_DELAY
  let reconnectTimer: ReturnType<typeof setTimeout> | null = null
  let destroyed = false
  const listeners = new Set<() => void>()
  const messageHandlers = new Map<string, Set<MessageHandler>>()

  function notify() {
    for (const listener of listeners) {
      listener()
    }
  }

  function setState(next: ConnectionState) {
    if (state !== next) {
      state = next
      notify()
    }
  }

  function clearReconnectTimer() {
    if (reconnectTimer !== null) {
      clearTimeout(reconnectTimer)
      reconnectTimer = null
    }
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

    if (ws) {
      ws.close()
      ws = null
    }

    setState('connecting')
    const socket = new WebSocket(url)

    socket.onopen = () => {
      if (destroyed) {
        socket.close()
        return
      }
      setState('connected')
      reconnectDelay = INITIAL_RECONNECT_DELAY
    }

    socket.onmessage = (event: MessageEvent) => {
      try {
        const message = JSON.parse(event.data as string) as WSMessage
        const handlers = messageHandlers.get(message.type)
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
      setState('disconnected')
      ws = null
      scheduleReconnect()
    }

    socket.onerror = () => {
      // onclose will fire after onerror, triggering reconnect
    }

    ws = socket
  }

  function destroy() {
    destroyed = true
    clearReconnectTimer()
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

  function getSnapshot(): ConnectionState {
    return state
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

  const connectionState = useSyncExternalStore(store.subscribe, store.getSnapshot)

  const send = useCallback((type: WSClientMessageType, payload?: unknown) => {
    store.send(type, payload)
  }, [store])

  const subscribeMessage = useCallback((type: string, handler: MessageHandler) => {
    return store.onMessage(type, handler)
  }, [store])

  return { connectionState, send, subscribe: subscribeMessage }
}
