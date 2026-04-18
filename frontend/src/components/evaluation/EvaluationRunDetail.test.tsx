import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import type { ModelInfo, TrainingStatus } from '../../lib/types'
import type { EvaluationJobAck, EvaluationJobStatus } from '../../lib/api'

const getModels = vi.fn<(title?: string, limit?: number) => Promise<ModelInfo[]>>()
const runEvaluation = vi.fn<(modelPath: string, botLevel: number, nGames: number) => Promise<EvaluationJobAck>>()
const getEvaluationStatus = vi.fn<(jobId: string) => Promise<EvaluationJobStatus>>()

vi.mock('../../lib/api', () => ({
  getModels: (title?: string, limit?: number) => getModels(title, limit),
  runEvaluation: (modelPath: string, botLevel: number, nGames: number) =>
    runEvaluation(modelPath, botLevel, nGames),
  getEvaluationStatus: (jobId: string) => getEvaluationStatus(jobId),
}))

// Shared training-state context is provided by TrainingStateProvider at
// runtime; tests render outside it so we mock the hook directly.
const mockTrainingState: { status: TrainingStatus } = {
  status: { state: 'stopped', currentStep: 0, currentEpisode: 0 },
}
vi.mock('../../hooks/useTrainingState', () => ({
  useTrainingState: () => mockTrainingState,
}))

import { EvaluationRunDetail } from './EvaluationRunDetail'

function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/evaluation/:title" element={<EvaluationRunDetail />} />
      </Routes>
    </MemoryRouter>,
  )
}

function model(overrides: Partial<ModelInfo> = {}): ModelInfo {
  return {
    path: 'exp-abc/run-baseline__exp-abc__200000.zip',
    sizeBytes: 4 * 1024 * 1024,
    filename: 'run-baseline__exp-abc__200000.zip',
    slug: 'run-baseline',
    title: 'run-baseline',
    step: 200000,
    createdAt: '2026-04-17T11:00:00Z',
    ...overrides,
  }
}

beforeEach(() => {
  getModels.mockReset()
  runEvaluation.mockReset()
  getEvaluationStatus.mockReset()
  try { sessionStorage.clear() } catch { /* ignore */ }
  mockTrainingState.status = { state: 'stopped', currentStep: 0, currentEpisode: 0 }
})

afterEach(() => {
  vi.restoreAllMocks()
})

describe('EvaluationRunDetail (FC-R7C level-2)', () => {
  it('renders breadcrumb + title decoded from URL', async () => {
    getModels.mockResolvedValueOnce([])
    renderAt('/evaluation/run-with%20space')
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent('run-with space')
    expect(screen.getByRole('link', { name: /All Trainings/ })).toHaveAttribute(
      'href', '/evaluation',
    )
    await waitFor(() => {
      // getModels called with the decoded title so BE can slugify.
      expect(getModels).toHaveBeenCalledWith('run-with space', undefined)
    })
  })

  it('renders a row per checkpoint and lets the user select one', async () => {
    getModels.mockResolvedValueOnce([
      model({ path: 'p/a__e__100.zip', filename: 'a__e__100.zip', step: 100 }),
      model({ path: 'p/a__e__200.zip', filename: 'a__e__200.zip', step: 200 }),
    ])
    renderAt('/evaluation/my-run')
    await waitFor(() => expect(screen.getAllByRole('radio').length).toBe(2))

    // Run button disabled until a selection is made.
    const runBtn = screen.getByRole('button', { name: /평가 실행/ })
    expect(runBtn).toBeDisabled()
    fireEvent.click(screen.getByLabelText('Select checkpoint step 200'))
    expect(runBtn).not.toBeDisabled()
  })

  it('renders the active-run badge when the live training matches this title', async () => {
    mockTrainingState.status = {
      state: 'running',
      currentStep: 1000,
      currentEpisode: 5,
      title: 'my-run',
    } as TrainingStatus
    getModels.mockResolvedValueOnce([])
    renderAt('/evaluation/my-run')
    await waitFor(() => {
      expect(screen.getByLabelText(/currently running/i)).toBeInTheDocument()
    })
  })

  it('shows the running-empty state when no checkpoints + run is live', async () => {
    mockTrainingState.status = {
      state: 'running',
      currentStep: 0,
      currentEpisode: 0,
      title: 'live-run',
    } as TrainingStatus
    getModels.mockResolvedValueOnce([])
    renderAt('/evaluation/live-run')
    await waitFor(() => {
      expect(screen.getByText(/체크포인트가 아직 없습니다/)).toBeInTheDocument()
    })
  })

  it('POSTs training:eval with selected checkpoint + bot_level + n_games', async () => {
    getModels.mockResolvedValueOnce([
      model({ path: 'exp/a__slug__500.zip', step: 500 }),
    ])
    runEvaluation.mockResolvedValueOnce({ jobId: 'job-1', state: 'pending' })
    // Mock status poll — report pending indefinitely so the button
    // stays in 'Running' state and doesn't flip back.
    getEvaluationStatus.mockResolvedValue({
      jobId: 'job-1',
      state: 'running',
      progress: { current: 0, total: 20 },
      result: null,
      error: null,
    })

    renderAt('/evaluation/my-run?bot_level=3')
    await waitFor(() => expect(screen.getByLabelText('Select checkpoint step 500')).toBeInTheDocument())
    fireEvent.click(screen.getByLabelText('Select checkpoint step 500'))
    // Bot level picked up from URL (3), default n_games = 20.
    fireEvent.click(screen.getByRole('button', { name: /평가 실행/ }))

    await waitFor(() => {
      expect(runEvaluation).toHaveBeenCalledWith('exp/a__slug__500.zip', 3, 20)
    })
  })

  it('surfaces a fetch error when getModels rejects', async () => {
    getModels.mockRejectedValueOnce(new Error('models endpoint down'))
    renderAt('/evaluation/broken-run')
    await waitFor(() => {
      expect(screen.getByRole('alert')).toHaveTextContent(/models endpoint down/)
    })
  })
})
