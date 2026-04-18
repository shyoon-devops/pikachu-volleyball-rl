import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { TrainingControls } from './TrainingControls'
import type { TrainingStatus, ConnectionState } from '../../lib/types'

function renderControls(overrides: {
  status?: Partial<TrainingStatus>
  connectionState?: ConnectionState
  reconnectAttempt?: number
} = {}) {
  const send = vi.fn()
  const onStart = vi.fn()

  const status: TrainingStatus = {
    state: 'stopped',
    currentStep: 0,
    currentEpisode: 0,
    ...overrides.status,
  }

  render(
    <TrainingControls
      status={status}
      connectionState={overrides.connectionState ?? 'connected'}
      reconnectAttempt={overrides.reconnectAttempt}
      send={send}
      onStart={onStart}
    />,
  )

  return { send, onStart }
}

describe('TrainingControls', () => {
  it('renders without crashing', () => {
    renderControls()
    expect(screen.getByText('Training Controls')).toBeInTheDocument()
  })

  it('shows Start button when stopped', () => {
    renderControls({ status: { state: 'stopped' } })
    expect(screen.getByText('Start')).toBeInTheDocument()
  })

  it('shows Stop button when running', () => {
    renderControls({ status: { state: 'running' } })
    expect(screen.getByText('Stop')).toBeInTheDocument()
  })

  it('shows Resume button when paused', () => {
    renderControls({ status: { state: 'paused' } })
    expect(screen.getByText('Resume')).toBeInTheDocument()
  })

  it('calls onStart when Start is clicked', () => {
    const { onStart } = renderControls({ status: { state: 'stopped' } })
    fireEvent.click(screen.getByText('Start'))
    expect(onStart).toHaveBeenCalledTimes(1)
  })

  it('renders exactly one Start-training button per state (duplicate-CTA guard)', () => {
    // Guards against the duplicate-Start-button regression. "Start" is
    // the distinguishing label; Pause/Resume coexist with Stop as a
    // secondary toggle and are NOT primary CTAs.
    const states: Array<TrainingStatus['state']> = ['stopped', 'running', 'paused']
    for (const state of states) {
      const { unmount } = render(
        <TrainingControls
          status={{ state, currentStep: 0, currentEpisode: 0 }}
          connectionState="connected"
          send={vi.fn()}
          onStart={vi.fn()}
        />,
      )
      const startButtons = screen
        .getAllByRole('button')
        .filter(b => b.textContent?.trim() === 'Start')
      expect(startButtons).toHaveLength(state === 'stopped' ? 1 : 0)
      unmount()
    }
  })

  it('shows Pause button when training is running', () => {
    renderControls({ status: { state: 'running' } })
    expect(screen.getByText('Pause')).toBeInTheDocument()
  })

  it('shows Resume (not Pause) when paused', () => {
    renderControls({ status: { state: 'paused' } })
    expect(screen.getByText('Resume')).toBeInTheDocument()
    expect(screen.queryByText('Pause')).not.toBeInTheDocument()
  })

  it('does not show Pause or Resume when stopped', () => {
    renderControls({ status: { state: 'stopped' } })
    expect(screen.queryByText('Pause')).not.toBeInTheDocument()
    expect(screen.queryByText('Resume')).not.toBeInTheDocument()
  })

  it('shows Stop alongside Pause/Resume while training is underway', () => {
    renderControls({ status: { state: 'running' } })
    expect(screen.getByText('Stop')).toBeInTheDocument()
    expect(screen.getByText('Pause')).toBeInTheDocument()
  })

  it('calls send with training:pause when Pause is clicked', () => {
    const { send } = renderControls({ status: { state: 'running' } })
    fireEvent.click(screen.getByText('Pause'))
    expect(send).toHaveBeenCalledWith('training:pause')
  })

  it('Pause button exposes accessible label', () => {
    renderControls({ status: { state: 'running' } })
    expect(screen.getByLabelText('Pause training')).toBeInTheDocument()
  })

  it('calls send with training:stop when Stop is clicked', () => {
    const { send } = renderControls({ status: { state: 'running' } })
    fireEvent.click(screen.getByText('Stop'))
    expect(send).toHaveBeenCalledWith('training:stop')
  })

  it('calls send with training:resume when Resume is clicked', () => {
    const { send } = renderControls({ status: { state: 'paused' } })
    fireEvent.click(screen.getByText('Resume'))
    expect(send).toHaveBeenCalledWith('training:resume')
  })

  it('renders bot level buttons L1-L5', () => {
    renderControls()
    for (let i = 1; i <= 5; i++) {
      expect(screen.getByText(`L${i}`)).toBeInTheDocument()
    }
  })

  it('calls send with training:set_level when bot level is clicked', () => {
    const { send } = renderControls({ status: { state: 'running' } })
    fireEvent.click(screen.getByText('L3'))
    expect(send).toHaveBeenCalledWith('training:set_level', { level: 3 })
  })

  it('bot level buttons fire training:set_level when state=stopped (Option A carry-over)', () => {
    // Option A depends on this path: before Start, the user picks a
    // level here; BE accepts training:set_level regardless of state
    // (backend/rl/trainer.py:223 — no state guard), updates
    // status.botLevel, and the next training:start (which omits
    // bot_level) picks it up via schemas.py:92.
    //
    // A regression that disabled these buttons while stopped would
    // silently trap Option A — the user could "pick" L5 but ship L1.
    const { send } = renderControls({ status: { state: 'stopped' } })
    const lvl5 = screen.getByLabelText('Set bot level to 5')
    expect(lvl5).not.toBeDisabled()
    fireEvent.click(lvl5)
    expect(send).toHaveBeenCalledWith('training:set_level', { level: 5 })
  })

  it('displays step and episode counters', () => {
    renderControls({ status: { currentStep: 5000, currentEpisode: 250 } })
    expect(screen.getByText('5,000')).toBeInTheDocument()
    expect(screen.getByText('250')).toBeInTheDocument()
  })

  it('disables buttons when disconnected', () => {
    renderControls({ status: { state: 'stopped' }, connectionState: 'disconnected' })
    const startBtn = screen.getByText('Start')
    expect(startBtn).toBeDisabled()
  })

  // ── Reconnect feedback (BUG-7 #19) ──
  it('shows "disconnected" when not connected and no reconnect attempts', () => {
    renderControls({ connectionState: 'disconnected' })
    expect(screen.getByText(/disconnected/i)).toBeInTheDocument()
  })

  it('shows reconnect attempt number when disconnected and reconnecting', () => {
    renderControls({ connectionState: 'disconnected', reconnectAttempt: 3 })
    expect(screen.getByText(/disconnected — retry 3/i)).toBeInTheDocument()
  })

  it('shows reconnect banner (role=alert) when disconnected with attempts', () => {
    renderControls({ connectionState: 'disconnected', reconnectAttempt: 2 })
    const alert = screen.getByRole('alert')
    expect(alert).toHaveTextContent(/Reconnecting.*attempt 2/i)
  })

  it('does NOT show reconnect banner when connected', () => {
    renderControls({ connectionState: 'connected', reconnectAttempt: 0 })
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })

  it('shows "reconnecting (attempt N)" when connecting after failures', () => {
    renderControls({ connectionState: 'connecting', reconnectAttempt: 4 })
    expect(screen.getByText(/reconnecting \(attempt 4\)/i)).toBeInTheDocument()
  })

  it('shows "connecting" on first attempt (reconnectAttempt=0)', () => {
    renderControls({ connectionState: 'connecting', reconnectAttempt: 0 })
    expect(screen.getByText(/^connecting$/i)).toBeInTheDocument()
  })

  // ── Accessibility (FE-5 #24) ──
  it('connection status has role=status for screen readers', () => {
    renderControls({ connectionState: 'connected' })
    expect(screen.getByRole('status')).toBeInTheDocument()
  })

  it('connection status exposes aria-label with connection state', () => {
    renderControls({ connectionState: 'connected', status: { state: 'running' } })
    const status = screen.getByRole('status')
    expect(status).toHaveAttribute('aria-label', expect.stringContaining('running'))
  })

  it('Start button has accessible label', () => {
    renderControls({ status: { state: 'stopped' } })
    expect(screen.getByLabelText('Start training')).toBeInTheDocument()
  })

  it('bot level buttons have accessible labels', () => {
    renderControls()
    for (let i = 1; i <= 5; i++) {
      expect(screen.getByLabelText(`Set bot level to ${i}`)).toBeInTheDocument()
    }
  })

  // ── Bot level active-state indicator (CRITICAL: "highlight current selection") ──
  it('marks the active bot level via data-active + .active class', () => {
    renderControls({ status: { botLevel: 3 } })

    const active = screen.getByLabelText('Set bot level to 3')
    expect(active).toHaveAttribute('data-active', 'true')
    expect(active).toHaveAttribute('aria-pressed', 'true')
    expect(active.className).toContain('active')

    // Siblings should be inactive.
    for (const level of [1, 2, 4, 5]) {
      const btn = screen.getByLabelText(`Set bot level to ${level}`)
      expect(btn).toHaveAttribute('data-active', 'false')
      expect(btn).toHaveAttribute('aria-pressed', 'false')
    }
  })

  it('shows no active bot level when status.botLevel is undefined', () => {
    renderControls()
    for (let i = 1; i <= 5; i++) {
      const btn = screen.getByLabelText(`Set bot level to ${i}`)
      expect(btn).toHaveAttribute('data-active', 'false')
      expect(btn).toHaveAttribute('aria-pressed', 'false')
    }
  })
})
