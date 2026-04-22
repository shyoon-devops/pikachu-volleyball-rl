import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import type { ConnectionState, GameRecord, GameState, LeagueUpdatePayload, TrainingMetrics, TrainingStatus } from '../../lib/types'
import type { EnvFramesMap } from '../../hooks/useTrainingState'

// Partial shape returned by useTrainingState — easy to swap per-test.
interface MockState {
  connectionState: ConnectionState
  reconnectAttempt: number
  status: TrainingStatus
  metrics: TrainingMetrics[]
  latestFrame: GameState | null
  recentGames: GameRecord[]
  envFrames: EnvFramesMap
  gameResultSeq: number
  leagueUpdate: LeagueUpdatePayload | null
  trainingMode: 'bot_ladder' | 'self_play'
  updatingPolicy: {
    active: boolean
    longGap: boolean
    source: 'event' | 'heuristic' | null
    step: number | null
  }
  send: () => void
}

const mockState: MockState = {
  connectionState: 'connecting',
  reconnectAttempt: 0,
  status: { state: 'stopped', currentStep: 0, currentEpisode: 0 },
  metrics: [],
  latestFrame: null,
  recentGames: [],
  envFrames: {},
  gameResultSeq: 0,
  leagueUpdate: null,
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
    envFrames: {},
    gameResultSeq: 0,
    leagueUpdate: null,
    trainingMode: 'bot_ladder' as const,
    updatingPolicy: { active: false, longGap: false, source: null, step: null },
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

  // ── Option A: bot_level is status-only (2026-04-12) ──
  it('training:start payload omits bot_level (BE substitutes status.bot_level)', () => {
    // Dashboard used to send `{ hyperparams, bot_level }` from local
    // state. Under Option A the form has no bot_level input and the
    // dashboard holds none, so Start must ship hyperparams only and
    // let BE carry over status.bot_level
    // (backend/app/models/schemas.py:92). Sending bot_level here would
    // silently reset a freshly-picked L-level.
    const send = vi.fn()
    resetMockState({
      connectionState: 'connected',
      status: { state: 'stopped', currentStep: 0, currentEpisode: 0, botLevel: 4 },
      send,
    })
    renderDashboard()

    fireEvent.click(screen.getByRole('button', { name: /start training/i }))

    expect(send).toHaveBeenCalledTimes(1)
    const call = send.mock.calls[0] as [string, Record<string, unknown>]
    expect(call[0]).toBe('training:start')
    expect(call[1]).toHaveProperty('hyperparams')
    expect(call[1]).not.toHaveProperty('bot_level')
  })

  // ── FC-R5: extended hyperparams unbundle into top-level + blob ──
  it('training:start unbundles top-level fields per HYPERPARAM_WIRE_POSITION', () => {
    // BE cc4daaf3 accepts total_timesteps / n_envs / n_epochs /
    // ent_coef / gae_lambda at the top level of the payload; the
    // remaining 5 fields ride inside `hyperparams`. Verify both
    // sides of the split.
    const send = vi.fn()
    resetMockState({
      connectionState: 'connected',
      status: { state: 'stopped', currentStep: 0, currentEpisode: 0, botLevel: 4 },
      send,
    })
    renderDashboard()

    fireEvent.click(screen.getByRole('button', { name: /start training/i }))

    expect(send).toHaveBeenCalledTimes(1)
    const [, payload] = send.mock.calls[0] as [string, Record<string, unknown>]
    // Top-level fields — must be on the outer payload, not in the blob.
    expect(payload).toHaveProperty('total_timesteps')
    expect(payload).toHaveProperty('n_envs')
    expect(payload).toHaveProperty('n_epochs')
    expect(payload).toHaveProperty('ent_coef')
    expect(payload).toHaveProperty('gae_lambda')
    // PPO ctor args — must live inside hyperparams.
    const blob = payload.hyperparams as Record<string, unknown>
    expect(blob).toHaveProperty('learning_rate')
    expect(blob).toHaveProperty('n_steps')
    expect(blob).toHaveProperty('batch_size')
    expect(blob).toHaveProperty('gamma')
    expect(blob).toHaveProperty('clip_range')
    // And the inverse — no top-level PPO-ctor leakage.
    expect(payload).not.toHaveProperty('learning_rate')
    expect(payload).not.toHaveProperty('gamma')
  })

  // ── v2.x Sprint 1: Opponent column + current-run league line + nav badge ──
  it('Recent Games table adds the Opponent column with a Rule L{n} fallback chip', () => {
    resetMockState({
      connectionState: 'connected',
      status: { state: 'running', currentStep: 100, currentEpisode: 1 },
      recentGames: [
        {
          id: 'g1',
          gameId: 'uuid-1',
          timestamp: '2026-04-18T10:00:00Z',
          botLevel: 3,
          score1: 15,
          score2: 10,
          winner: 1,
          durationFrames: 4200,
          rallyCount: 8,
        } as GameRecord,
      ],
    })
    renderDashboard()
    expect(screen.getByRole('columnheader', { name: 'Opponent' })).toBeInTheDocument()
    // Row renders the rule fallback since opponentCheckpointId is absent.
    expect(screen.getByLabelText('Opponent: Rule L3')).toBeInTheDocument()
  })

  it('hides CurrentRunLeagueLine when trainingMode is bot_ladder', () => {
    resetMockState({
      connectionState: 'connected',
      status: {
        state: 'running',
        currentStep: 100,
        currentEpisode: 1,
        experimentId: 'exp-live',
      } as TrainingStatus,
      trainingMode: 'bot_ladder',
      leagueUpdate: {
        topN: [
          {
            id: 'x',
            elo: 1500,
            wins: 30,
            losses: 10,
            games: 40,
            admittedAt: '2026-04-18T00:00:00Z',
            source: 'training',
            experimentId: 'exp-live',
          },
        ],
        poolSize: 12,
        championId: 'x',
        generation: 2,
        totalMatches: 100,
        sinceLastBroadcast: 64,
      },
    })
    renderDashboard()
    expect(screen.queryByText(/Elo 1500/)).toBeNull()
  })

  it('renders CurrentRunLeagueLine when self_play + experiment is in topN', () => {
    resetMockState({
      connectionState: 'connected',
      status: {
        state: 'running',
        currentStep: 500,
        currentEpisode: 2,
        experimentId: 'exp-live',
      } as TrainingStatus,
      trainingMode: 'self_play',
      leagueUpdate: {
        topN: [
          {
            id: 'foo',
            elo: 1800,
            wins: 20,
            losses: 5,
            games: 25,
            admittedAt: '2026-04-18T00:00:00Z',
            source: 'training',
            experimentId: 'other',
          },
          {
            id: 'bar',
            elo: 1500,
            wins: 30,
            losses: 10,
            games: 40,
            admittedAt: '2026-04-18T00:00:00Z',
            source: 'training',
            experimentId: 'exp-live',
          },
        ],
        poolSize: 14,
        championId: 'foo',
        generation: 3,
        totalMatches: 200,
        sinceLastBroadcast: 64,
      },
    })
    renderDashboard()
    expect(screen.getByText(/Elo 1500/)).toBeInTheDocument()
    expect(screen.getByText(/#2 of 14/)).toBeInTheDocument()
  })

  // ── v2.x Sprint 1: opponent mode + sampling in training:start ──
  it('training:start payload includes mode + sampling (default bot_ladder + pfsp)', () => {
    const send = vi.fn()
    resetMockState({
      connectionState: 'connected',
      status: { state: 'stopped', currentStep: 0, currentEpisode: 0 },
      send,
    })
    renderDashboard()
    fireEvent.click(screen.getByRole('button', { name: /start training/i }))
    const [, payload] = send.mock.calls[0] as [string, Record<string, unknown>]
    expect(payload.mode).toBe('bot_ladder')
    // Default sampling is always sent for payload-shape stability, BE
    // ignores it when mode=bot_ladder per handlers.py:_build_league_*.
    expect(payload.sampling).toBe('pfsp')
  })

  // ── v2.x Sprint 4/5: algorithm in training:start (ADR 0017 §3,
  // ADR 0018 §4 — enum now `ppo | sac | dreamer_v3`) ──
  it('training:start payload carries ppo → sac → dreamer_v3 without any FE gate', () => {
    const send = vi.fn()
    resetMockState({
      connectionState: 'connected',
      status: { state: 'stopped', currentStep: 0, currentEpisode: 0 },
      send,
    })
    renderDashboard()
    // Default — first click sends ppo.
    fireEvent.click(screen.getByRole('button', { name: /start training/i }))
    const [, firstPayload] = send.mock.calls[0] as [string, Record<string, unknown>]
    expect(firstPayload.algorithm).toBe('ppo')
    // Switch to SAC.
    fireEvent.click(screen.getByRole('radio', { name: /^SAC/ }))
    fireEvent.click(screen.getByRole('button', { name: /start training/i }))
    const [, secondPayload] = send.mock.calls[1] as [string, Record<string, unknown>]
    expect(secondPayload.algorithm).toBe('sac')
    // Switch to Dreamer V3 — the S5 enum extension.
    fireEvent.click(screen.getByRole('radio', { name: /Dreamer V3/ }))
    fireEvent.click(screen.getByRole('button', { name: /start training/i }))
    const [, thirdPayload] = send.mock.calls[2] as [string, Record<string, unknown>]
    expect(thirdPayload.algorithm).toBe('dreamer_v3')
  })

  // ── FC-R6G: title in training:start payload ──
  it('training:start payload includes a (possibly empty) title field', () => {
    // BE T1 (a7351e57) accepts `title: str | None`; empty triggers
    // BE auto-gen. FE sends verbatim without gating on empty.
    const send = vi.fn()
    resetMockState({
      connectionState: 'connected',
      status: { state: 'stopped', currentStep: 0, currentEpisode: 0 },
      send,
    })
    renderDashboard()
    fireEvent.click(screen.getByRole('button', { name: /start training/i }))
    const [, payload] = send.mock.calls[0] as [string, Record<string, unknown>]
    // Title key present on the outer payload (not nested in hyperparams).
    expect(payload).toHaveProperty('title')
    expect(typeof payload.title).toBe('string')
    // Default form state has no user input → empty string allowed.
    expect(payload.title).toBe('')
  })

  // R7A follow-up — React error #310 ("Rendered more hooks than
  // during the previous render"). Skeleton gate used to sit between
  // the hooks; transitioning from skeleton (connecting + no data) to
  // the real UI (connected + data) ran a different number of hooks
  // across consecutive renders and React tore down the tree. The
  // gate now lives below every hook, so this transition must be
  // stable.
  it('transitions from skeleton to real UI without hook-order violation', () => {
    resetMockState({ connectionState: 'connecting' })
    const { rerender } = renderDashboard()
    expect(screen.getByRole('status', { name: /loading dashboard/i })).toBeInTheDocument()

    // Simulate WS connect + data landing → gate flips to false.
    resetMockState({
      connectionState: 'connected',
      status: { state: 'stopped', currentStep: 0, currentEpisode: 0 },
      metrics: [
        { step: 1, episode: 1, meanReward: 0, winRate: 0, policyLoss: 0, valueLoss: 0 } as TrainingMetrics,
      ],
    })
    expect(() =>
      rerender(
        <MemoryRouter>
          <Dashboard />
        </MemoryRouter>,
      ),
    ).not.toThrow()
    expect(screen.queryByRole('status', { name: /loading dashboard/i })).not.toBeInTheDocument()
    expect(screen.getByTestId('game-canvas')).toBeInTheDocument()
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

  // FC-R7G + FC-R8a: tabs follow observed envFrames ONLY while
  // training is active; otherwise the bar is replaced by a
  // placeholder. The old `observed` inflation bug (stale keys from
  // a prior run fueling max() against a smaller new run) is
  // eliminated by ignoring the form value entirely for tab count.
  it('hides tabs (shows "no active run" placeholder) when stopped', () => {
    const staleFrames: EnvFramesMap = {}
    for (let i = 0; i < 16; i++) {
      staleFrames[i] = {
        envId: i,
        frame: null,
        score: [0, 0],
        stateName: 'play',
        stepCount: 0,
      } as unknown as EnvFramesMap[number]
    }
    resetMockState({
      connectionState: 'connected',
      status: { state: 'stopped', currentStep: 0, currentEpisode: 0 },
      envFrames: staleFrames,
    })
    renderDashboard()
    // No tabs rendered — placeholder surfaces instead.
    expect(screen.queryAllByRole('tab')).toHaveLength(0)
    expect(screen.getByText(/No active training/)).toBeInTheDocument()
  })

  it('shows exactly as many tabs as observed envFrames while running', () => {
    const runningFrames: EnvFramesMap = {}
    for (let i = 0; i < 4; i++) {
      runningFrames[i] = {
        envId: i,
        frame: null,
        score: [0, 0],
        stateName: 'play',
        stepCount: 0,
      } as unknown as EnvFramesMap[number]
    }
    resetMockState({
      connectionState: 'connected',
      status: {
        state: 'running',
        currentStep: 100,
        currentEpisode: 1,
        experimentId: 'exp-small',
      },
      envFrames: runningFrames,
    })
    renderDashboard()
    const tabs = screen.getAllByRole('tab')
    expect(tabs.length).toBe(4)
  })

  it('shows a "waiting" placeholder while running + no env frames yet (refresh window)', () => {
    resetMockState({
      connectionState: 'connected',
      status: {
        state: 'running',
        currentStep: 0,
        currentEpisode: 0,
        experimentId: 'exp-fresh',
      },
      envFrames: {},
    })
    renderDashboard()
    expect(screen.queryAllByRole('tab')).toHaveLength(0)
    expect(screen.getByText(/Waiting for environment data/)).toBeInTheDocument()
  })
})
