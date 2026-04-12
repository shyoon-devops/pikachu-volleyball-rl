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
  const onStartWithParams = vi.fn()

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
      onStartWithParams={onStartWithParams}
    />,
  )

  return { send, onStartWithParams }
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

  it('calls onStartWithParams when Start is clicked', () => {
    const { onStartWithParams } = renderControls({ status: { state: 'stopped' } })
    fireEvent.click(screen.getByText('Start'))
    expect(onStartWithParams).toHaveBeenCalledTimes(1)
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
})
