import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import type { ConnectionState, GameRecord, GameState, TrainingMetrics, TrainingStatus } from '../../lib/types'

// Partial shape returned by useTrainingState — easy to swap per-test.
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
  connectionState: 'connecting',
  reconnectAttempt: 0,
  status: { state: 'stopped', currentStep: 0, currentEpisode: 0 },
  metrics: [],
  latestFrame: null,
  recentGames: [],
  send: vi.fn(),
}

vi.mock('../../hooks/useTrainingState', () => ({
  useTrainingState: () => mockState,
}))

// GameCanvas uses PixiJS which doesn't run cleanly in jsdom — stub it.
vi.mock('../game/GameCanvas', () => ({
  GameCanvas: () => <div data-testid="game-canvas" />,
}))

// Recharts needs ResizeObserver + the real chart output adds noise.
vi.mock('./MetricsChart', () => ({
  MetricsChart: ({ label }: { label: string }) => <div data-testid={`metrics-${label}`} />,
}))

import { Dashboard } from './Dashboard'

function renderDashboard() {
  return render(
    <MemoryRouter>
      <Dashboard />
    </MemoryRouter>,
  )
}

function resetMockState(overrides: Partial<MockState> = {}) {
  Object.assign(mockState, {
    connectionState: 'connecting' as ConnectionState,
    reconnectAttempt: 0,
    status: { state: 'stopped', currentStep: 0, currentEpisode: 0 },
    metrics: [],
    latestFrame: null,
    recentGames: [],
    send: vi.fn(),
    ...overrides,
  })
}

describe('Dashboard loading state', () => {
  beforeEach(() => {
    resetMockState()
  })

  it('shows the skeleton while still connecting with no data', () => {
    resetMockState({ connectionState: 'connecting' })
    renderDashboard()
    expect(screen.getByRole('status', { name: /loading dashboard/i })).toBeInTheDocument()
  })

  it('does not show the skeleton once connected', () => {
    resetMockState({ connectionState: 'connected' })
    renderDashboard()
    expect(screen.queryByRole('status', { name: /loading dashboard/i })).not.toBeInTheDocument()
    // Real dashboard UI should be up
    expect(screen.getByTestId('game-canvas')).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: /recent games/i })).toBeInTheDocument()
  })

  it('renders exactly one Start button on the whole dashboard when stopped', () => {
    // Duplicate-Start-button regression guard. Previously the dashboard
    // shipped two CTAs: one in TrainingControls ("Start") and one in
    // HyperparamForm ("Start Training"). There must be exactly one now.
    resetMockState({
      connectionState: 'connected',
      status: { state: 'stopped', currentStep: 0, currentEpisode: 0 },
    })
    renderDashboard()
    const startButtons = screen
      .getAllByRole('button')
      .filter(b => /^(start|start training)$/i.test(b.textContent?.trim() ?? ''))
    expect(startButtons).toHaveLength(1)
    expect(startButtons[0]).toHaveTextContent(/^Start$/)
  })

  it('toggles primary CTA label Start → Stop when training is running', () => {
    resetMockState({
      connectionState: 'connected',
      status: { state: 'running', currentStep: 10, currentEpisode: 1 },
    })
    renderDashboard()
    expect(screen.queryByRole('button', { name: /start training/i })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: /stop training/i })).toBeInTheDocument()
  })

  it('page loads with active training → shows Stop, not Start (refresh-while-running regression)', () => {
    // Reproduces the CRITICAL bug: on refresh with training already running,
    // the UI used to show the default 'stopped' state → Start button → no
    // way to issue Stop. After the REST status-sync fix, the hook hydrates
    // from /api/training/status before first paint, so the mocked state
    // already carries state=running and the primary CTA is Stop.
    resetMockState({
      connectionState: 'connected',
      status: { state: 'running', currentStep: 12345, currentEpisode: 7 },
    })
    renderDashboard()
    expect(screen.getByRole('button', { name: /stop training/i })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /start training/i })).not.toBeInTheDocument()
    // Primary CTA must be enabled — the bug manifested as a dead Stop.
    const stop = screen.getByRole('button', { name: /stop training/i })
    expect(stop).not.toBeDisabled()
  })

  it('does not show the skeleton on a mid-session disconnect if we already have data', () => {
    resetMockState({
      connectionState: 'disconnected',
      reconnectAttempt: 2,
      metrics: [
        { step: 1, episode: 1, meanReward: 0.1, winRate: 0.2, policyLoss: 0.01, valueLoss: 0.01 } as TrainingMetrics,
      ],
    })
    renderDashboard()
    expect(screen.queryByRole('status', { name: /loading dashboard/i })).not.toBeInTheDocument()
  })

  it('does not show the skeleton when reconnecting mid-session with data present', () => {
    resetMockState({
      connectionState: 'connecting',
      reconnectAttempt: 1,
      latestFrame: {
        ball: { x: 0, y: 0, vx: 0, vy: 0 },
        p1: { x: 0, y: 0, vx: 0, vy: 0, diving: false, stunned: false },
        p2: { x: 0, y: 0, vx: 0, vy: 0, diving: false, stunned: false },
        score1: 0,
        score2: 0,
      } as unknown as GameState,
    })
    renderDashboard()
    expect(screen.queryByRole('status', { name: /loading dashboard/i })).not.toBeInTheDocument()
  })
})
