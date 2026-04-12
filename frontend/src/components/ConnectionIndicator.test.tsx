import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import type { ConnectionState, GameRecord, GameState, TrainingMetrics, TrainingStatus } from '../lib/types'

interface MockState {
  connectionState: ConnectionState
  reconnectAttempt: number
  status: TrainingStatus
  metrics: TrainingMetrics[]
  latestFrame: GameState | null
  recentGames: GameRecord[]
  send: () => void
}

const mockState: MockState = {
  connectionState: 'connected',
  reconnectAttempt: 0,
  status: { state: 'stopped', currentStep: 0, currentEpisode: 0 },
  metrics: [],
  latestFrame: null,
  recentGames: [],
  send: vi.fn(),
}

vi.mock('../hooks/useTrainingState', () => ({
  useTrainingState: () => mockState,
}))

import { ConnectionIndicator } from './ConnectionIndicator'

function setState(overrides: Partial<MockState>) {
  Object.assign(mockState, {
    connectionState: 'connected' as ConnectionState,
    reconnectAttempt: 0,
    ...overrides,
  })
}

describe('ConnectionIndicator', () => {
  it('renders an Online label when connected', () => {
    setState({ connectionState: 'connected', reconnectAttempt: 0 })
    render(<ConnectionIndicator />)
    expect(screen.getByText(/^online$/i)).toBeInTheDocument()
  })

  it('renders Connecting… on first attempt (reconnectAttempt=0)', () => {
    setState({ connectionState: 'connecting', reconnectAttempt: 0 })
    render(<ConnectionIndicator />)
    expect(screen.getByText(/^connecting/i)).toBeInTheDocument()
  })

  it('shows the attempt count while reconnecting', () => {
    setState({ connectionState: 'connecting', reconnectAttempt: 3 })
    render(<ConnectionIndicator />)
    expect(screen.getByText(/reconnecting/i)).toBeInTheDocument()
    expect(screen.getByText(/#3/)).toBeInTheDocument()
  })

  it('shows Offline with retry count when disconnected mid-reconnect', () => {
    setState({ connectionState: 'disconnected', reconnectAttempt: 2 })
    render(<ConnectionIndicator />)
    expect(screen.getByText(/offline/i)).toBeInTheDocument()
    expect(screen.getByText(/#2/)).toBeInTheDocument()
  })

  it('shows plain Offline when fully disconnected with no retry yet', () => {
    setState({ connectionState: 'disconnected', reconnectAttempt: 0 })
    render(<ConnectionIndicator />)
    expect(screen.getByText(/^offline$/i)).toBeInTheDocument()
  })

  it('exposes an aria-label describing the connection state', () => {
    setState({ connectionState: 'connecting', reconnectAttempt: 4 })
    render(<ConnectionIndicator />)
    const el = screen.getByRole('status')
    expect(el).toHaveAttribute('aria-label', expect.stringMatching(/reconnect/i))
    expect(el).toHaveAttribute('aria-label', expect.stringContaining('4'))
  })

  it('applies a distinct CSS modifier per state', () => {
    setState({ connectionState: 'connected' })
    const { rerender } = render(<ConnectionIndicator />)
    expect(screen.getByRole('status').className).toMatch(/connected/)

    setState({ connectionState: 'disconnected', reconnectAttempt: 0 })
    rerender(<ConnectionIndicator />)
    expect(screen.getByRole('status').className).toMatch(/disconnected/)

    setState({ connectionState: 'disconnected', reconnectAttempt: 5 })
    rerender(<ConnectionIndicator />)
    expect(screen.getByRole('status').className).toMatch(/reconnecting/)
  })
})
