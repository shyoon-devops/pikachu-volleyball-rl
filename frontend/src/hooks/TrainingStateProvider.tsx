import type { ReactNode } from 'react'
import { TrainingStateContext, useTrainingStateImpl } from './useTrainingState'

/**
 * Wraps the app so every consumer shares one WebSocket connection.
 * Without this, each component calling useTrainingState would open its
 * own socket (createWebSocketStore runs per useState initializer).
 */
export function TrainingStateProvider({ children }: { children: ReactNode }) {
  const value = useTrainingStateImpl()
  return (
    <TrainingStateContext.Provider value={value}>
      {children}
    </TrainingStateContext.Provider>
  )
}
