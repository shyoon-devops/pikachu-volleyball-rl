import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import type { LeagueStandings, LeagueUpdatePayload } from '../../lib/types'

const getLeagueStandings = vi.fn<(limit?: number) => Promise<LeagueStandings>>()

vi.mock('../../lib/api', async () => {
  const actual = await vi.importActual<typeof import('../../lib/api')>('../../lib/api')
  return {
    ...actual,
    getLeagueStandings: (limit?: number) => getLeagueStandings(limit),
  }
})

// WS hook: leagueUpdate swapped per-test.
const mockHook: { leagueUpdate: LeagueUpdatePayload | null } = { leagueUpdate: null }
vi.mock('../../hooks/useTrainingState', () => ({
  useTrainingState: () => mockHook,
}))

import { LeaguePanel } from './LeaguePanel'

beforeEach(() => {
  getLeagueStandings.mockReset()
  mockHook.leagueUpdate = null
})

afterEach(() => {
  vi.restoreAllMocks()
})

describe('LeaguePanel (v2.x S1)', () => {
  it('shows the empty-pool fallback hint when the pool is empty', async () => {
    getLeagueStandings.mockResolvedValueOnce({
      top: [],
      championId: null,
      generation: 0,
      poolSize: 32,
      totalCheckpoints: 0,
    })
    render(<LeaguePanel />)
    await waitFor(() => {
      expect(screen.getByText(/Pool empty/i)).toBeInTheDocument()
    })
    // Leaderboard renders its own empty-state copy.
    expect(screen.getByText(/No checkpoints admitted yet/i)).toBeInTheDocument()
  })

  it('renders the top-10 leaderboard from REST standings', async () => {
    getLeagueStandings.mockResolvedValueOnce({
      top: [
        {
          id: 'run-baseline__abc12345__200000',
          elo: 1382,
          wins: 30,
          losses: 20,
          games: 50,
          admittedAt: '2026-04-17T10:00:00Z',
          source: 'training',
        },
        {
          id: 'anchor-L1',
          elo: 600,
          wins: 0,
          losses: 0,
          games: 0,
          admittedAt: '2026-01-01T00:00:00Z',
          source: 'anchor',
        },
      ],
      championId: 'run-baseline__abc12345__200000',
      generation: 2,
      poolSize: 32,
      totalCheckpoints: 12,
    })
    render(<LeaguePanel />)
    await waitFor(() => {
      // Champion short-id appears in both the pool header and the
      // leaderboard row — assert at least one node renders.
      expect(screen.getAllByText('abc12345__200000').length).toBeGreaterThan(0)
    })
    expect(screen.getByText(/Gen 2/)).toBeInTheDocument()
    // Champion row gets the crown + highlight class.
    const crowns = screen.getAllByLabelText('Champion')
    expect(crowns.length).toBeGreaterThanOrEqual(1)
    // Anchor row renders the source chip.
    expect(screen.getByText('anchor')).toBeInTheDocument()
    // Pool chip shows filled / cap.
    expect(screen.getByText('12 / 32')).toBeInTheDocument()
  })

  it('WS leagueUpdate overrides the REST snapshot when both are present', async () => {
    getLeagueStandings.mockResolvedValueOnce({
      top: [
        {
          id: 'rest-entry__aaa__1000',
          elo: 1100,
          wins: 10,
          losses: 5,
          games: 15,
          admittedAt: '2026-04-16T00:00:00Z',
          source: 'training',
        },
      ],
      championId: 'rest-entry__aaa__1000',
      generation: 1,
      poolSize: 32,
      totalCheckpoints: 5,
    })
    mockHook.leagueUpdate = {
      topN: [
        {
          id: 'ws-entry__bbb__2000',
          elo: 1500,
          wins: 40,
          losses: 10,
          games: 50,
          admittedAt: '2026-04-18T00:00:00Z',
          source: 'training',
        },
      ],
      poolSize: 18,
      championId: 'ws-entry__bbb__2000',
      generation: 3,
      totalMatches: 1024,
      sinceLastBroadcast: 64,
      recent: [],
    }
    render(<LeaguePanel />)
    // WS content wins over REST. Short-id appears in the champion
    // header chip AND the leaderboard row — both should carry the
    // WS-derived value.
    await waitFor(() => {
      expect(screen.getAllByText('bbb__2000').length).toBeGreaterThan(0)
    })
    expect(screen.getByText('18 / 32')).toBeInTheDocument()
    expect(screen.getByText(/Gen 3/)).toBeInTheDocument()
    // REST entry not rendered.
    expect(screen.queryByText('aaa__1000')).toBeNull()
  })

  it('renders recent matches only from the WS payload (not REST)', async () => {
    getLeagueStandings.mockResolvedValueOnce({
      top: [], championId: null, generation: 0, poolSize: 32, totalCheckpoints: 0,
    })
    mockHook.leagueUpdate = {
      topN: [],
      poolSize: 0,
      championId: null,
      generation: 0,
      totalMatches: 3,
      sinceLastBroadcast: 3,
      recent: [
        { opponentId: 'opp-one__xx__100', winner: 'rl', duration: 4200, deltaElo: 12 },
        { opponentId: 'opp-two__yy__200', winner: 'bot', duration: 3800, deltaElo: -8 },
      ],
    }
    render(<LeaguePanel />)
    await waitFor(() => {
      expect(screen.getByText('xx__100')).toBeInTheDocument()
    })
    expect(screen.getByText('+12')).toBeInTheDocument()
    expect(screen.getByText('-8')).toBeInTheDocument()
  })

  it('surfaces a REST error when getLeagueStandings rejects and WS is absent', async () => {
    getLeagueStandings.mockRejectedValueOnce(new Error('standings endpoint down'))
    render(<LeaguePanel />)
    await waitFor(() => {
      expect(screen.getByRole('alert')).toHaveTextContent(/standings endpoint down/)
    })
  })
})
