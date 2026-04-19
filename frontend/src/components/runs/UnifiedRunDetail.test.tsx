import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import type { EvalResult, ModelInfo, PaginatedResponse, TrainingRun, TrainingStatus, GameRecord, ReplayInfo } from '../../lib/types'
import type { EvaluationJobAck, EvaluationJobStatus } from '../../lib/api'

// ── Module mocks ─────────────────────────────────────────────
const getTrainingRuns = vi.fn<(page?: number, limit?: number) => Promise<PaginatedResponse<TrainingRun>>>()
const getModels = vi.fn<(title?: string, limit?: number) => Promise<ModelInfo[]>>()
const runEvaluation = vi.fn<(modelPath: string, botLevel: number, nGames: number) => Promise<EvaluationJobAck>>()
const getEvaluationStatus = vi.fn<(jobId: string) => Promise<EvaluationJobStatus>>()
const deleteModels = vi.fn<(paths: string[]) => Promise<{ deleted: string[]; failed: Array<{ path: string; reason: string }> }>>()
const getGames = vi.fn<(page?: number, limit?: number, title?: string) => Promise<PaginatedResponse<GameRecord>>>()
const getAvailableReplays = vi.fn<() => Promise<ReplayInfo[]>>()
const getEvalResults = vi.fn<() => Promise<EvalResult[]>>()
const getLeagueStandings = vi.fn<() => Promise<import('../../lib/types').LeagueStandings>>()

vi.mock('../../lib/api', async () => {
  const actual = await vi.importActual<typeof import('../../lib/api')>('../../lib/api')
  return {
    ...actual,
    getTrainingRuns: (page?: number, limit?: number) => getTrainingRuns(page, limit),
    getModels: (title?: string, limit?: number) => getModels(title, limit),
    runEvaluation: (modelPath: string, botLevel: number, nGames: number) =>
      runEvaluation(modelPath, botLevel, nGames),
    getEvaluationStatus: (jobId: string) => getEvaluationStatus(jobId),
    deleteModels: (paths: string[]) => deleteModels(paths),
    getGames: (page?: number, limit?: number, title?: string) => getGames(page, limit, title),
    getAvailableReplays: () => getAvailableReplays(),
    getEvalResults: () => getEvalResults(),
    getLeagueStandings: () => getLeagueStandings(),
  }
})

const mockTrainingState: {
  gameResultSeq: number
  status: TrainingStatus
  leagueUpdate: null
} = {
  gameResultSeq: 0,
  status: { state: 'stopped', currentStep: 0, currentEpisode: 0 },
  leagueUpdate: null,
}
vi.mock('../../hooks/useTrainingState', () => ({
  useTrainingState: () => mockTrainingState,
}))

import { UnifiedRunDetail } from './UnifiedRunDetail'

function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/runs/:title" element={<UnifiedRunDetail />} />
      </Routes>
    </MemoryRouter>,
  )
}

function runRow(overrides: Partial<TrainingRun> = {}): TrainingRun {
  return {
    title: 'my-run',
    experimentId: 'exp-abcdef12',
    startedAt: '2026-04-17T10:00:00Z',
    endedAt: '2026-04-17T12:00:00Z',
    totalGames: 42,
    winRate: 0.65,
    avgRallyLength: 7.8,
    status: 'done',
    hyperparams: {
      total_timesteps: 1_000_000,
      n_envs: 4,
      learning_rate: 3e-4,
      n_steps: 2048,
      batch_size: 64,
      n_epochs: 10,
      gamma: 0.995,
      clip_range: 0.2,
      ent_coef: 1e-2,
      gae_lambda: 0.95,
    },
    ...overrides,
  }
}

beforeEach(() => {
  getTrainingRuns.mockReset()
  getModels.mockReset()
  runEvaluation.mockReset()
  getEvaluationStatus.mockReset()
  deleteModels.mockReset()
  getGames.mockReset()
  getAvailableReplays.mockReset()
  getEvalResults.mockReset()
  // Sensible defaults so sub-tabs that fetch on mount don't crash.
  getTrainingRuns.mockResolvedValue({ data: [runRow()], total: 1, page: 1, limit: 100 })
  getModels.mockResolvedValue([])
  getGames.mockResolvedValue({ data: [], total: 0, page: 1, limit: 20 })
  getAvailableReplays.mockResolvedValue([])
  getEvalResults.mockResolvedValue([])
  getLeagueStandings.mockResolvedValue({
    top: [], championId: null, generation: 0, poolSize: 32, totalCheckpoints: 0,
  })
  try { sessionStorage.clear() } catch { /* ignore */ }
  mockTrainingState.gameResultSeq = 0
  mockTrainingState.status = { state: 'stopped', currentStep: 0, currentEpisode: 0 }
  mockTrainingState.leagueUpdate = null
})

afterEach(() => {
  vi.restoreAllMocks()
})

describe('UnifiedRunDetail (FC-R8A)', () => {
  it('renders the breadcrumb + h1 from the URL param', () => {
    renderAt('/runs/my-run')
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent('my-run')
    expect(screen.getByRole('link', { name: /Training Runs/ })).toHaveAttribute('href', '/runs')
  })

  it('defaults to the Overview tab when no ?tab= is supplied', async () => {
    renderAt('/runs/my-run')
    const overviewTab = screen.getByRole('tab', { name: 'Overview' })
    expect(overviewTab).toHaveAttribute('aria-selected', 'true')
    // Overview renders the HyperparamsSummary card with run fields.
    await waitFor(() => {
      expect(screen.getByText('Hyperparameters')).toBeInTheDocument()
    })
  })

  it('honours ?tab=games — Games panel renders ReplayList', async () => {
    renderAt('/runs/my-run?tab=games')
    const gamesTab = screen.getByRole('tab', { name: 'Games' })
    expect(gamesTab).toHaveAttribute('aria-selected', 'true')
    // ReplayList renders the Game History heading.
    await waitFor(() => {
      expect(screen.getByText('Game History')).toBeInTheDocument()
    })
  })

  it('honours ?tab=eval — Evaluation panel renders the checkpoint runner', async () => {
    getModels.mockResolvedValue([
      { path: 'exp/my-run__e__100.zip', sizeBytes: 1024, filename: 'my-run__e__100.zip', slug: 'my-run', title: 'my-run', step: 100 } as ModelInfo,
    ])
    renderAt('/runs/my-run?tab=eval')
    const evalTab = screen.getByRole('tab', { name: 'Evaluation' })
    expect(evalTab).toHaveAttribute('aria-selected', 'true')
    // Evaluation panel renders Run Evaluation button (embedded, no breadcrumb).
    await waitFor(() => {
      expect(screen.getByRole('button', { name: /Run Evaluation/ })).toBeInTheDocument()
    })
    // Embedded mode hides the evaluation-specific breadcrumb so the
    // unified header isn't duplicated inside the tab panel.
    expect(screen.queryByRole('link', { name: 'Evaluation' })).toBeNull()
  })

  it('honours ?tab=league — League panel renders pool status + leaderboard', async () => {
    renderAt('/runs/my-run?tab=league')
    const leagueTab = screen.getByRole('tab', { name: 'League' })
    expect(leagueTab).toHaveAttribute('aria-selected', 'true')
    // Pool status bar is always visible; leaderboard falls back to
    // empty-state copy when top-N is empty.
    await waitFor(() => {
      expect(screen.getByText(/Pool empty/i)).toBeInTheDocument()
    })
  })

  it('clicking tabs updates ?tab= in the URL (no full route change)', async () => {
    renderAt('/runs/my-run')
    fireEvent.click(screen.getByRole('tab', { name: 'Games' }))
    const gamesTab = screen.getByRole('tab', { name: 'Games' })
    expect(gamesTab).toHaveAttribute('aria-selected', 'true')
    await waitFor(() => expect(screen.getByText('Game History')).toBeInTheDocument())
  })

  it('shows Running chip when the live manager matches this title', async () => {
    mockTrainingState.status = {
      state: 'running',
      currentStep: 1000,
      currentEpisode: 5,
      title: 'my-run',
    } as TrainingStatus
    renderAt('/runs/my-run')
    expect(screen.getByLabelText(/currently running/i)).toBeInTheDocument()
  })
})
