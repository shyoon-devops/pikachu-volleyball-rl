import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
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

function evalResult(botLevel: number, winRate: number, overrides: Partial<EvalResult> = {}): EvalResult {
  return {
    modelPath: 'models/latest.zip',
    botLevel,
    nGames: 50,
    winRate,
    avgScore: 0.8,
    avgRallyLength: 4.2,
    ...overrides,
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
  // Wipe session storage so a prior test's active-job id doesn't
  // cross-contaminate the next test's mount.
  try { sessionStorage.clear() } catch { /* ignore in SSR-like envs */ }
})

afterEach(() => {
  vi.restoreAllMocks()
  try { sessionStorage.clear() } catch { /* ignore */ }
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

    render(<MemoryRouter><EvalPanel /></MemoryRouter>)

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

    render(<MemoryRouter><EvalPanel /></MemoryRouter>)

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

    render(<MemoryRouter><EvalPanel /></MemoryRouter>)
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

describe('EvalPanel — mount-resume via sessionStorage (FC-R3, 2026-04-18)', () => {
  // The panel unmounts on tab navigation; before this fix the active
  // jobId lived in React state and died with the component. Users
  // returning to /evaluation saw the Run button lit back up, clicked,
  // and got a 409 "already in progress" error. sessionStorage bridges
  // the unmount gap without needing a BE-side "active job" endpoint.

  function getRunButton(): HTMLButtonElement {
    const btn = document.querySelector('.eval-form-submit')
    if (!btn) throw new Error('Run Evaluation button not mounted')
    return btn as HTMLButtonElement
  }

  it('resumes polling on mount when sessionStorage has a stored job id', async () => {
    sessionStorage.setItem('eval:active_job_id', 'job-resumed')
    mockGetEvaluationStatus
      .mockResolvedValueOnce(jobStatus('running', {
        jobId: 'job-resumed',
        progress: { current: 17, total: 50 },
      }))

    render(<MemoryRouter><EvalPanel /></MemoryRouter>)

    await waitFor(() => {
      expect(mockGetEvaluationStatus).toHaveBeenCalledWith('job-resumed')
    })
    // Button label reflects the resumed progress.
    await waitFor(
      () => expect(getRunButton()).toHaveTextContent(/Running\s+17\/50/),
      { timeout: 2000 },
    )
  }, 10_000)

  it('clears stale sessionStorage when the resumed /status returns done', async () => {
    sessionStorage.setItem('eval:active_job_id', 'job-stale')
    mockGetEvaluationStatus
      .mockResolvedValueOnce(jobStatus('done', {
        jobId: 'job-stale',
        progress: { current: 50, total: 50 },
      }))

    render(<MemoryRouter><EvalPanel /></MemoryRouter>)

    await waitFor(() => {
      expect(sessionStorage.getItem('eval:active_job_id')).toBeNull()
    })
    // UI should be idle (Run Evaluation label, enabled) — nothing to resume.
    await waitFor(() => expect(getRunButton()).toHaveTextContent('Run Evaluation'))
  })

  it('clears stale sessionStorage when the resumed /status 404s', async () => {
    sessionStorage.setItem('eval:active_job_id', 'job-evicted')
    mockGetEvaluationStatus.mockRejectedValueOnce(new Error('404 Job not found'))

    render(<MemoryRouter><EvalPanel /></MemoryRouter>)

    await waitFor(() => {
      expect(sessionStorage.getItem('eval:active_job_id')).toBeNull()
    })
  })

  it('persists a new job_id in sessionStorage on successful POST', async () => {
    mockRunEvaluation.mockResolvedValueOnce({ jobId: 'job-persisted', state: 'pending' })
    mockGetEvaluationStatus.mockResolvedValue(jobStatus('running', {
      jobId: 'job-persisted',
      progress: { current: 1, total: 50 },
    }))

    render(<MemoryRouter><EvalPanel /></MemoryRouter>)
    await waitFor(() => expect(getRunButton()).toBeEnabled())
    fireEvent.click(getRunButton())

    await waitFor(() => {
      expect(sessionStorage.getItem('eval:active_job_id')).toBe('job-persisted')
    })
  })
})

describe('EvalPanel — timestamp column + bot_level retention (FC-R6F)', () => {
  it('renders a KST-formatted timestamp for each result row', async () => {
    mockGetEvalResults.mockResolvedValueOnce([
      evalResult(3, 0.72, { timestamp: '2026-04-17T17:32:22Z' }),
    ])

    render(<MemoryRouter><EvalPanel /></MemoryRouter>)

    // 17:32:22Z → 02:32:22 KST (+9h) the next day.
    await waitFor(() => {
      expect(screen.getByText(/2026-04-18 02:32:22/)).toBeInTheDocument()
    })
  })

  it('renders an em-dash when a result row lacks a timestamp (legacy record)', async () => {
    mockGetEvalResults.mockResolvedValueOnce([
      evalResult(3, 0.72), // no timestamp
    ])

    render(<MemoryRouter><EvalPanel /></MemoryRouter>)

    await waitFor(() => {
      // 72.0% is the row's win-rate text; the em-dash sits in the
      // adjacent Time cell.
      expect(screen.getByText(/72.0%/)).toBeInTheDocument()
    })
    // Em-dash is ubiquitous elsewhere (e.g. other '—' fallbacks in
    // the page chrome). Tighten by anchoring on the row: first cell
    // of the only result row is the timestamp.
    const firstRow = document.querySelector('.eval-results-table tbody tr')
    expect(firstRow?.firstElementChild?.textContent).toBe('—')
  })

  it('pre-populates the bot-level select from ?bot_level=4 on mount', async () => {
    render(
      <MemoryRouter initialEntries={['/evaluation?bot_level=4']}>
        <EvalPanel />
      </MemoryRouter>,
    )

    const select = await screen.findByRole('combobox')
    expect((select as HTMLSelectElement).value).toBe('4')
  })

  it('writes bot_level changes back to the URL (replace, no history clutter)', async () => {
    // Spy on the location — react-router's MemoryRouter keeps search
    // params on `window.history` via its wrapper. We inspect the
    // select value round-trip instead, which proves the setter
    // wired the param.
    render(<MemoryRouter><EvalPanel /></MemoryRouter>)
    const select = await screen.findByRole('combobox')
    fireEvent.change(select, { target: { value: '5' } })
    await waitFor(() => {
      expect((select as HTMLSelectElement).value).toBe('5')
    })
  })

  it('falls back to L1 for a bogus ?bot_level=foo value', async () => {
    render(
      <MemoryRouter initialEntries={['/evaluation?bot_level=foo']}>
        <EvalPanel />
      </MemoryRouter>,
    )
    const select = await screen.findByRole('combobox')
    expect((select as HTMLSelectElement).value).toBe('1')
  })
})
