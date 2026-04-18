import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import type { ModelInfo, TrainingRun, PaginatedResponse } from '../../lib/types'

const getTrainingRuns = vi.fn<(page?: number, limit?: number) => Promise<PaginatedResponse<TrainingRun>>>()
// FC-R7F: evaluation mode fetches `/api/models` to count checkpoints
// per slug. History mode never invokes this — we still mock it so a
// stray call doesn't hit the network.
const getModels = vi.fn<(title?: string, limit?: number) => Promise<ModelInfo[]>>()

vi.mock('../../lib/api', async () => {
  const actual = await vi.importActual<typeof import('../../lib/api')>('../../lib/api')
  return {
    ...actual,
    getTrainingRuns: (page?: number, limit?: number) => getTrainingRuns(page, limit),
    getModels: (title?: string, limit?: number) => getModels(title, limit),
  }
})

// FC-R7B: TrainingRunList reads `gameResultSeq` from the shared
// training-state hook to trigger a refetch whenever a new game:result
// lands on the ws. Tests render in isolation (no TrainingStateProvider),
// so we mock the hook directly. The mocked object is mutated by
// individual tests via `mockTrainingState.gameResultSeq = N` + rerender
// to simulate the live bump.
const mockTrainingState = { gameResultSeq: 0 }
vi.mock('../../hooks/useTrainingState', () => ({
  useTrainingState: () => mockTrainingState,
}))

import { TrainingRunList } from './TrainingRunList'

function run(overrides: Partial<TrainingRun> = {}): TrainingRun {
  return {
    title: 'run-baseline-1',
    experimentId: 'exp-abc',
    startedAt: '2026-04-17T10:00:00Z',
    endedAt: '2026-04-17T12:00:00Z',
    totalGames: 42,
    winRate: 0.65,
    avgRallyLength: 7.8,
    status: 'done',
    ...overrides,
  }
}

function page(runs: TrainingRun[]): PaginatedResponse<TrainingRun> {
  return { data: runs, total: runs.length, page: 1, limit: 50 }
}

beforeEach(() => {
  getTrainingRuns.mockReset()
  getModels.mockReset()
  getModels.mockResolvedValue([])
  mockTrainingState.gameResultSeq = 0
})

afterEach(() => {
  vi.restoreAllMocks()
})

describe('TrainingRunList (FC-R6H level-1)', () => {
  it('renders one row per training run with link to /history/:title', async () => {
    getTrainingRuns.mockResolvedValueOnce(
      page([run({ title: 'run-a' }), run({ title: 'run-b' })]),
    )
    render(
      <MemoryRouter>
        <TrainingRunList />
      </MemoryRouter>,
    )
    await waitFor(() => {
      expect(screen.getByRole('link', { name: 'run-a' })).toHaveAttribute(
        'href',
        '/history/run-a',
      )
    })
    expect(screen.getByRole('link', { name: 'run-b' })).toBeInTheDocument()
  })

  it('URL-encodes titles with spaces / special characters', async () => {
    getTrainingRuns.mockResolvedValueOnce(
      page([run({ title: 'run with space & symbol' })]),
    )
    render(
      <MemoryRouter>
        <TrainingRunList />
      </MemoryRouter>,
    )
    await waitFor(() => {
      // Both the desktop table row AND the mobile card render a
      // link (CSS hides one via media query; jsdom ignores MQs).
      // Assert every link's href is encoded identically.
      const links = screen.getAllByRole('link', { name: /run with space/ })
      expect(links.length).toBeGreaterThan(0)
      for (const link of links) {
        expect(link.getAttribute('href')).toBe('/history/run%20with%20space%20%26%20symbol')
      }
    })
  })

  it('renders status chip with running pulse for live runs', async () => {
    getTrainingRuns.mockResolvedValueOnce(
      page([run({ title: 'run-live', status: 'running' })]),
    )
    render(
      <MemoryRouter>
        <TrainingRunList />
      </MemoryRouter>,
    )
    await waitFor(() => {
      const chip = screen.getAllByLabelText(/Run status:/)[0]
      expect(chip.className).toContain('training-run-status-chip--running')
    })
  })

  it('filters client-side by title substring (debounced)', async () => {
    getTrainingRuns.mockResolvedValueOnce(
      page([
        run({ title: 'run-alpha' }),
        run({ title: 'run-beta' }),
        run({ title: 'experiment-control' }),
      ]),
    )
    render(
      <MemoryRouter>
        <TrainingRunList />
      </MemoryRouter>,
    )
    await waitFor(() => expect(screen.getByRole('link', { name: 'run-alpha' })).toBeInTheDocument())

    fireEvent.change(screen.getByLabelText('Search training runs by title'), {
      target: { value: 'run-' },
    })

    // 200ms debounce → wait for beta to still be visible, control gone.
    await waitFor(
      () => {
        expect(screen.queryByRole('link', { name: 'experiment-control' })).toBeNull()
      },
      { timeout: 800 },
    )
    expect(screen.getByRole('link', { name: 'run-alpha' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'run-beta' })).toBeInTheDocument()
  })

  it('shows the search-zero empty state with a clear action', async () => {
    getTrainingRuns.mockResolvedValueOnce(
      page([run({ title: 'run-alpha' })]),
    )
    render(
      <MemoryRouter>
        <TrainingRunList />
      </MemoryRouter>,
    )
    await waitFor(() => expect(screen.getByRole('link', { name: 'run-alpha' })).toBeInTheDocument())

    fireEvent.change(screen.getByLabelText('Search training runs by title'), {
      target: { value: 'nonexistent' },
    })
    await waitFor(
      () => expect(screen.getByText(/No results for/)).toBeInTheDocument(),
      { timeout: 800 },
    )
    // Click-to-clear restores the original list.
    fireEvent.click(screen.getByRole('button', { name: /Clear search/ }))
    await waitFor(
      () => expect(screen.getByRole('link', { name: 'run-alpha' })).toBeInTheDocument(),
      { timeout: 800 },
    )
  })

  it('shows the no-runs empty state with a CTA to the dashboard', async () => {
    getTrainingRuns.mockResolvedValueOnce(page([]))
    render(
      <MemoryRouter>
        <TrainingRunList />
      </MemoryRouter>,
    )
    await waitFor(() => {
      expect(screen.getByText(/No training runs yet/)).toBeInTheDocument()
    })
    expect(screen.getByRole('link', { name: /Start Training/ })).toHaveAttribute('href', '/')
  })

  it('surfaces a fetch error without crashing', async () => {
    getTrainingRuns.mockRejectedValueOnce(new Error('runs endpoint down'))
    render(
      <MemoryRouter>
        <TrainingRunList />
      </MemoryRouter>,
    )
    await waitFor(() => {
      expect(screen.getByRole('alert')).toHaveTextContent(/runs endpoint down/)
    })
  })

  // FC-R7B: a bump on `gameResultSeq` from the shared hook must
  // re-run `getTrainingRuns` so the list picks up the freshly-landed
  // game without the user manually refreshing. Mirrors the same path
  // we wired in ReplayList.
  it('refetches runs when gameResultSeq bumps (live game:result sync)', async () => {
    getTrainingRuns.mockResolvedValueOnce(page([run({ title: 'run-a', totalGames: 1 })]))
    const { rerender } = render(
      <MemoryRouter>
        <TrainingRunList />
      </MemoryRouter>,
    )
    await waitFor(() => {
      expect(screen.getByRole('link', { name: 'run-a' })).toBeInTheDocument()
    })
    expect(getTrainingRuns).toHaveBeenCalledTimes(1)

    // Simulate a ws game:result landing → seq bump + rerender. The
    // effect's dep array watches gameResultSeq, so a new fetch fires.
    getTrainingRuns.mockResolvedValueOnce(page([run({ title: 'run-a', totalGames: 2 })]))
    mockTrainingState.gameResultSeq = 1
    rerender(
      <MemoryRouter>
        <TrainingRunList />
      </MemoryRouter>,
    )
    await waitFor(() => {
      expect(getTrainingRuns).toHaveBeenCalledTimes(2)
    })
  })

  // FC-R7F eval variant: label change + checkpoint count + disabled
  // rows when a run has zero models.
  it('evaluation mode: renders the eval header + Checkpoints column', async () => {
    getTrainingRuns.mockResolvedValueOnce(page([run({ title: 'my-run' })]))
    getModels.mockResolvedValueOnce([
      // 2 checkpoints for my-run, 0 for absent titles.
      { path: 'x/my-run__e__100.zip', sizeBytes: 1024, slug: 'my-run', filename: 'x' } as ModelInfo,
      { path: 'x/my-run__e__200.zip', sizeBytes: 1024, slug: 'my-run', filename: 'x' } as ModelInfo,
    ])
    render(
      <MemoryRouter>
        <TrainingRunList linkBase="/evaluation/" mode="evaluation" />
      </MemoryRouter>,
    )
    await waitFor(() => {
      expect(screen.getByRole('heading', { name: /Select Training for Evaluation/i })).toBeInTheDocument()
    })
    // Checkpoints column visible.
    expect(screen.getByRole('columnheader', { name: /Checkpoints/i })).toBeInTheDocument()
    // Count badge renders from the model fetch. Desktop table + mobile
    // card both render one (CSS hides one per breakpoint but jsdom
    // ignores media queries), so use `getAllByLabelText`.
    await waitFor(() => {
      expect(screen.getAllByLabelText(/2 checkpoints/).length).toBeGreaterThan(0)
    })
  })

  it('evaluation mode: zero-checkpoint runs disable the row link', async () => {
    getTrainingRuns.mockResolvedValueOnce(page([run({ title: 'empty-run' })]))
    getModels.mockResolvedValueOnce([]) // no checkpoints for any title
    render(
      <MemoryRouter>
        <TrainingRunList linkBase="/evaluation/" mode="evaluation" />
      </MemoryRouter>,
    )
    // Row title renders but without a Link. Count shows "0".
    await waitFor(() => {
      expect(screen.getAllByText('0').length).toBeGreaterThan(0)
    })
    // No link for empty-run in the table — the title cell is a
    // disabled span with the no-models tooltip.
    expect(screen.queryByRole('link', { name: 'empty-run' })).toBeNull()
    expect(screen.getAllByTitle(/No saved checkpoints/).length).toBeGreaterThan(0)
  })

  // FC-R7A regression guard: qa-observed crash where runs
  // aggregate returned rows with null fields (title / numeric /
  // status) — rendering must not throw.
  it('renders a row whose every nullable field is null/zero without crashing', async () => {
    getTrainingRuns.mockResolvedValueOnce(
      page([
        {
          title: null as unknown as string,
          experimentId: null,
          startedAt: null,
          endedAt: null,
          totalGames: null as unknown as number,
          winRate: Number.NaN,
          avgRallyLength: null as unknown as number,
          status: null as unknown as string,
        },
      ]),
    )
    render(
      <MemoryRouter>
        <TrainingRunList />
      </MemoryRouter>,
    )
    // Title falls back to "untitled"; numeric cells fall back to 0.
    await waitFor(() => {
      expect(screen.getAllByRole('link', { name: /untitled/ }).length).toBeGreaterThan(0)
    })
    // No error banner.
    expect(screen.queryByRole('alert')).toBeNull()
    // Status chip defaults to "Finished" when BE status is null.
    expect(screen.getAllByText('Finished').length).toBeGreaterThan(0)
  })
})
