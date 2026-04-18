import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import type {
  EvalResult,
  ModelInfo,
} from '../../lib/types'
import type { EvaluationJobAck, EvaluationJobStatus } from '../../lib/api'

// Stub the chart component — it uses Recharts + Canvas which jsdom
// can't render meaningfully, and we don't need the visual here.
vi.mock('./EvalChart', () => ({
  EvalChart: () => <div data-testid="eval-chart" />,
}))

// Mock the entire api surface so each test controls the job lifecycle.
const mockGetModels = vi.fn<() => Promise<ModelInfo[]>>()
const mockGetEvalResults = vi.fn<() => Promise<EvalResult[]>>()
const mockRunEvaluation = vi.fn<(model: string, level: number, n: number) => Promise<EvaluationJobAck>>()
const mockGetEvaluationStatus = vi.fn<(jobId: string) => Promise<EvaluationJobStatus>>()

vi.mock('../../lib/api', () => ({
  getModels: () => mockGetModels(),
  getEvalResults: () => mockGetEvalResults(),
  runEvaluation: (model: string, level: number, n: number) =>
    mockRunEvaluation(model, level, n),
  getEvaluationStatus: (jobId: string) => mockGetEvaluationStatus(jobId),
}))

import { EvalPanel } from './EvalPanel'

function makeModel(path: string): ModelInfo {
  return { path, sizeBytes: 1024 }
}

function jobStatus(
  state: EvaluationJobStatus['state'],
  overrides: Partial<EvaluationJobStatus> = {},
): EvaluationJobStatus {
  return {
    jobId: 'job-1',
    state,
    progress: { current: 0, total: 50 },
    result: null,
    error: null,
    ...overrides,
  }
}

function evalResult(botLevel: number, winRate: number): EvalResult {
  return {
    modelPath: 'models/latest.zip',
    botLevel,
    nGames: 50,
    winRate,
    avgScore: 0.8,
    avgRallyLength: 4.2,
  }
}

beforeEach(() => {
  mockGetModels.mockReset()
  mockGetEvalResults.mockReset()
  mockRunEvaluation.mockReset()
  mockGetEvaluationStatus.mockReset()
  // Default: one model, empty results.
  mockGetModels.mockResolvedValue([makeModel('models/latest.zip')])
  mockGetEvalResults.mockResolvedValue([])
})

afterEach(() => {
  vi.restoreAllMocks()
})

describe('EvalPanel — async job polling (2026-04-18)', () => {
  // The Run Evaluation button carries the `.eval-form-submit` class, so
  // we scope queries to that rather than the ambiguous `button` role
  // (there are also L1..L5 filter buttons in the panel).
  function getRunButton(): HTMLButtonElement {
    const btn = document.querySelector('.eval-form-submit')
    if (!btn) throw new Error('Run Evaluation button not mounted')
    return btn as HTMLButtonElement
  }

  it('POSTs /run, flips the button to Running, then polls /status until done', async () => {
    mockRunEvaluation.mockResolvedValueOnce({ jobId: 'job-abc', state: 'pending' })
    // Three-step job: pending → running → done. Each call returns the
    // next state so pollOnce loops through them naturally.
    mockGetEvaluationStatus
      .mockResolvedValueOnce(jobStatus('pending'))
      .mockResolvedValueOnce(jobStatus('running', {
        progress: { current: 12, total: 50 },
      }))
      .mockResolvedValueOnce(jobStatus('done', {
        progress: { current: 50, total: 50 },
        result: evalResult(3, 0.72),
      }))
    // After `done` lands, the panel refetches /results.
    mockGetEvalResults.mockResolvedValueOnce([]).mockResolvedValueOnce([
      evalResult(3, 0.72),
    ])

    render(<EvalPanel />)

    await waitFor(() => expect(getRunButton()).toBeEnabled())
    fireEvent.click(getRunButton())

    // POST fired with the panel's current form selections.
    await waitFor(() => expect(mockRunEvaluation).toHaveBeenCalledTimes(1))
    expect(mockRunEvaluation).toHaveBeenCalledWith('models/latest.zip', 1, 50)

    // First poll tick reads `pending` → button shows "Running 0/50".
    await waitFor(
      () => expect(getRunButton()).toHaveTextContent(/Running\s+0\/50/),
      { timeout: 2000 },
    )

    // Second poll tick reads `running` with 12/50 → progress updates.
    await waitFor(
      () => expect(getRunButton()).toHaveTextContent(/Running\s+12\/50/),
      { timeout: 3000 },
    )

    // Third poll tick reads `done` → button returns to idle label.
    await waitFor(
      () => expect(getRunButton()).toHaveTextContent('Run Evaluation'),
      { timeout: 6000 },
    )
    expect(getRunButton()).toBeEnabled()

    // Results list re-fetched; row landed in the table.
    await waitFor(() => {
      expect(screen.getByText(/72.0%/)).toBeInTheDocument()
    })
  }, 15_000)

  it('renders a friendly busy message on 409 without spamming errors', async () => {
    mockRunEvaluation.mockRejectedValueOnce(new Error('409 Evaluation already in progress'))

    render(<EvalPanel />)

    await waitFor(() => expect(getRunButton()).toBeEnabled())
    fireEvent.click(getRunButton())

    await waitFor(() => {
      expect(screen.getByText(/already in progress/i)).toBeInTheDocument()
    })
    // Button stays disabled so the user can't keep retrying.
    expect(getRunButton()).toBeDisabled()
    // No poll loop was started — we never got a job id.
    expect(mockGetEvaluationStatus).not.toHaveBeenCalled()
  })

  it('shows the failed-job error and returns to idle', async () => {
    mockRunEvaluation.mockResolvedValueOnce({ jobId: 'job-fail', state: 'pending' })
    mockGetEvaluationStatus.mockResolvedValueOnce(jobStatus('failed', {
      error: 'Model checkpoint corrupt',
    }))

    render(<EvalPanel />)
    await waitFor(() => expect(getRunButton()).toBeEnabled())
    fireEvent.click(getRunButton())

    await waitFor(() => {
      expect(screen.getByText('Model checkpoint corrupt')).toBeInTheDocument()
    })
    // Button back to idle label so user can retry after fixing the input.
    await waitFor(() => expect(getRunButton()).toHaveTextContent('Run Evaluation'))
    expect(getRunButton()).toBeEnabled()
  }, 10_000)
})
