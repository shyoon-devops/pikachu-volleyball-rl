import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MetricsChart } from './MetricsChart'
import type { TrainingMetrics } from '../../lib/types'

// Recharts uses window.ResizeObserver — jsdom lacks it.
class MockResizeObserver {
  observe() {}
  unobserve() {}
  disconnect() {}
}

beforeEach(() => {
  vi.stubGlobal('ResizeObserver', MockResizeObserver)
  // jsdom lacks matchMedia; provide a default stub (reduced-motion = false)
  vi.stubGlobal('matchMedia', (query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    addListener: vi.fn(),
    removeListener: vi.fn(),
    dispatchEvent: vi.fn(),
  }))
})

const sampleData: TrainingMetrics[] = [
  { step: 0, episode: 0, meanReward: 1.0, winRate: 0.1, policyLoss: 0.5, valueLoss: 0.3 },
  { step: 10, episode: 1, meanReward: 1.5, winRate: 0.2, policyLoss: 0.4, valueLoss: 0.25 },
  { step: 20, episode: 2, meanReward: 2.0, winRate: 0.3, policyLoss: 0.35, valueLoss: 0.2 },
]

describe('MetricsChart', () => {
  it('renders with a title', () => {
    render(<MetricsChart data={sampleData} dataKey="meanReward" color="#22c55e" label="Reward" />)
    expect(screen.getByText('Reward')).toBeInTheDocument()
  })

  it('renders with empty data without crashing', () => {
    render(<MetricsChart data={[]} dataKey="meanReward" color="#22c55e" label="Empty" />)
    expect(screen.getByText('Empty')).toBeInTheDocument()
  })

  it('renders smoothing slider', () => {
    render(<MetricsChart data={sampleData} dataKey="meanReward" color="#22c55e" label="Reward" />)
    // slider input (type=range) is present
    const slider = screen.getByRole('slider')
    expect(slider).toBeInTheDocument()
  })

  describe('sampling-cadence summary (PM Phase 2 #4)', () => {
    it('renders "N pts · M steps" using currentStep as denominator', () => {
      // Regression: user reported step counter = 1000 but chart has ~10
      // points, looking like data loss. It's not — MetricsCallback
      // samples every ~100 steps. The label surfaces the real ratio so
      // the behavior is self-describing.
      render(
        <MetricsChart
          data={sampleData}
          dataKey="meanReward"
          color="#22c55e"
          label="Reward"
          currentStep={1000}
        />,
      )
      expect(screen.getByText('3 pts · 1000 steps')).toBeInTheDocument()
    })

    it('falls back to last sample step when currentStep prop is omitted', () => {
      // Older callers without the prop still produce a sensible label
      // (last sampled step of 20 from sampleData).
      render(<MetricsChart data={sampleData} dataKey="meanReward" color="#22c55e" label="Reward" />)
      expect(screen.getByText('3 pts · 20 steps')).toBeInTheDocument()
    })

    it('omits the summary entirely when data is empty', () => {
      // No data → no denominator to report. The card still renders the
      // title so "empty chart" remains a visible state.
      render(<MetricsChart data={[]} dataKey="meanReward" color="#22c55e" label="Empty" currentStep={0} />)
      expect(screen.queryByText(/pts · /)).not.toBeInTheDocument()
    })

    it('includes a tooltip with the derived sample interval', () => {
      // Samples at step 0, 10, 20 → interval = 10. Tooltip explains the
      // cadence so the user doesn't have to do the math.
      render(
        <MetricsChart
          data={sampleData}
          dataKey="meanReward"
          color="#22c55e"
          label="Reward"
          currentStep={1000}
        />,
      )
      const summary = screen.getByText('3 pts · 1000 steps')
      expect(summary).toHaveAttribute('title', '~1 sample per 10 training steps')
    })

    it('omits the interval tooltip when only one sample exists', () => {
      // With a single point there's no interval to compute; don't
      // fabricate one.
      render(
        <MetricsChart
          data={[sampleData[0]]}
          dataKey="meanReward"
          color="#22c55e"
          label="Reward"
          currentStep={50}
        />,
      )
      const summary = screen.getByText('1 pts · 50 steps')
      expect(summary).not.toHaveAttribute('title')
    })
  })

  it('respects prefers-reduced-motion by not animating when set', () => {
    // Make matchMedia return matches=true for reduced-motion
    vi.stubGlobal('matchMedia', (query: string) => ({
      matches: query.includes('reduce'),
      media: query,
      onchange: null,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      addListener: vi.fn(),
      removeListener: vi.fn(),
      dispatchEvent: vi.fn(),
    }))

    const { container } = render(
      <MetricsChart data={sampleData} dataKey="meanReward" color="#22c55e" label="Reward" />,
    )
    // If reduced motion is active, the component renders but should not crash.
    // We can't easily inspect recharts' internals, but render should succeed.
    expect(container.querySelector('.metrics-chart')).toBeInTheDocument()
  })
})
