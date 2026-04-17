import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { ReplayList } from './ReplayList'
import type { GameRecord, ReplayInfo } from '../../lib/types'

// Pin formatBotLevel by mocking the api module so we control both
// fetches independently — the unified-list behaviour is the join
// between games and replays, so test must verify both inputs land
// on the same row.

const getGames = vi.fn<
  (page: number, limit: number) => Promise<{ data: GameRecord[]; total: number; page: number; limit: number }>
>()
const getAvailableReplays = vi.fn<() => Promise<ReplayInfo[]>>()

vi.mock('../../lib/api', () => ({
  getGames: (page: number, limit: number) => getGames(page, limit),
  getAvailableReplays: () => getAvailableReplays(),
}))

function gameRow(overrides: Partial<GameRecord> = {}): GameRecord {
  // BE shape: `id` is the Mongo ObjectId hex (unique row key), `gameId`
  // is the UUID4 minted at game-end and used as the replay file stem.
  // The unified-list join MUST use `gameId`, not `id`.
  return {
    id: 'mongo-objectid-1',
    gameId: 'uuid-game-1',
    timestamp: '2026-04-18T01:00:00Z',
    botLevel: 3,
    score1: 15,
    score2: 12,
    winner: 1,
    durationFrames: 4500,
    rallyCount: 9,
    ...overrides,
  }
}

function replayRow(overrides: Partial<ReplayInfo> = {}): ReplayInfo {
  return {
    // Default replay matches the default game's UUID, NOT its Mongo id.
    gameId: 'uuid-game-1',
    sizeBytes: 4096,
    createdAt: 1713400000,
    ...overrides,
  }
}

beforeEach(() => {
  getGames.mockReset()
  getAvailableReplays.mockReset()
})

afterEach(() => {
  vi.restoreAllMocks()
})

describe('ReplayList — unified games + replays (B2)', () => {
  it('renders one row per game with a Watch button when a replay file exists', async () => {
    // Mongo ObjectId hex (g.id) and replay UUID4 (g.gameId) are
    // different — the join key is the UUID. This test pins the F1
    // regression: pre-fix code joined on g.id and the Watch button
    // never lit up.
    getGames.mockResolvedValue({
      data: [gameRow({ id: 'mongo-objectid-x', gameId: 'uuid-watched' })],
      total: 1,
      page: 1,
      limit: 20,
    })
    getAvailableReplays.mockResolvedValue([replayRow({ gameId: 'uuid-watched' })])

    render(
      <MemoryRouter>
        <ReplayList />
      </MemoryRouter>,
    )

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /Watch replay for game uuid-wat/ })).toBeTruthy()
    })
    // Old "Available Replays" section header must not be in the unified view.
    expect(screen.queryByText('Available Replays')).toBeNull()
  })

  it('renders an em-dash for games without a replay file (no Watch button)', async () => {
    getGames.mockResolvedValue({
      data: [gameRow({ id: 'mongo-no-replay', gameId: 'uuid-no-replay' })],
      total: 1,
      page: 1,
      limit: 20,
    })
    // Empty replay inventory — game still renders, replay column shows
    // "—" so the user sees the game existed even if the .msgpack is gone.
    getAvailableReplays.mockResolvedValue([])

    render(
      <MemoryRouter>
        <ReplayList />
      </MemoryRouter>,
    )

    await waitFor(() => {
      expect(screen.getByLabelText('No replay file available')).toBeTruthy()
    })
    expect(screen.queryByRole('button', { name: /Watch replay/ })).toBeNull()
  })

  it('joins games and replays by gameId (extra replays without a game row are ignored)', async () => {
    // Two games, but only one has a replay file. The replay inventory
    // also contains an entry for an unrelated gameId (e.g. a game on
    // a later page) — that orphan must NOT spawn an extra row, since
    // the table is driven by the games list, not the replays list.
    getGames.mockResolvedValue({
      data: [
        gameRow({ id: 'mongo-a', gameId: 'uuid-with-replay' }),
        gameRow({ id: 'mongo-b', gameId: 'uuid-without' }),
      ],
      total: 2,
      page: 1,
      limit: 20,
    })
    getAvailableReplays.mockResolvedValue([
      replayRow({ gameId: 'uuid-with-replay' }),
      replayRow({ gameId: 'uuid-orphan-not-on-this-page' }),
    ])

    render(
      <MemoryRouter>
        <ReplayList />
      </MemoryRouter>,
    )

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /Watch replay for game uuid-wit/ })).toBeTruthy()
    })
    // The orphan replay must not appear as its own row.
    expect(screen.queryByText(/uuid-orphan/)).toBeNull()
    // Two data rows total (the row count check is implicit via game IDs).
    const watchButtons = screen.queryAllByRole('button', { name: /Watch replay/ })
    expect(watchButtons.length).toBe(1)
  })

  it('falls back to id when gameId is missing (legacy doc — UUID stored as _id)', async () => {
    // Pre-port docs occasionally stored the UUID directly as `_id`,
    // leaving `game_id` field empty. The fallback `g.gameId ?? g.id`
    // must still resolve those rows so older history doesn't go dark.
    getGames.mockResolvedValue({
      data: [{
        id: 'uuid-legacy',
        // gameId intentionally omitted
        timestamp: '2026-04-18T01:00:00Z',
        botLevel: 2,
        score1: 15,
        score2: 7,
        winner: 1,
        durationFrames: 3000,
        rallyCount: 5,
      }],
      total: 1,
      page: 1,
      limit: 20,
    })
    getAvailableReplays.mockResolvedValue([replayRow({ gameId: 'uuid-legacy' })])

    render(
      <MemoryRouter>
        <ReplayList />
      </MemoryRouter>,
    )

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /Watch replay for game uuid-leg/ })).toBeTruthy()
    })
  })

  it('keeps rendering games when getAvailableReplays() rejects (degraded mode)', async () => {
    // Filesystem inventory failure should not blank the page — the
    // user can still read the game stats; only the Watch column goes
    // dark.
    getGames.mockResolvedValue({
      data: [gameRow({ id: 'mongo-1', gameId: 'uuid-1' })],
      total: 1,
      page: 1,
      limit: 20,
    })
    getAvailableReplays.mockRejectedValue(new Error('replays endpoint down'))

    render(
      <MemoryRouter>
        <ReplayList />
      </MemoryRouter>,
    )

    await waitFor(() => {
      expect(screen.getByLabelText('No replay file available')).toBeTruthy()
    })
    // No global error banner — the games fetch succeeded.
    expect(screen.queryByText(/Failed to load games/)).toBeNull()
  })

  it('shows the empty-state message when there are no games', async () => {
    getGames.mockResolvedValue({ data: [], total: 0, page: 1, limit: 20 })
    getAvailableReplays.mockResolvedValue([])

    render(
      <MemoryRouter>
        <ReplayList />
      </MemoryRouter>,
    )

    await waitFor(() => {
      expect(screen.getByText('No games recorded yet.')).toBeTruthy()
    })
  })
})
