import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { ReplayControls } from './ReplayControls'

function renderReplayControls(overrides: Partial<{
  isPlaying: boolean
  speed: number
  currentFrame: number
  totalFrames: number
}> = {}) {
  const onTogglePlay = vi.fn()
  const onSpeedChange = vi.fn()
  const onSeek = vi.fn()

  render(
    <ReplayControls
      isPlaying={overrides.isPlaying ?? false}
      speed={overrides.speed ?? 1}
      currentFrame={overrides.currentFrame ?? 0}
      totalFrames={overrides.totalFrames ?? 100}
      onTogglePlay={onTogglePlay}
      onSpeedChange={onSpeedChange}
      onSeek={onSeek}
    />,
  )

  return { onTogglePlay, onSpeedChange, onSeek }
}

describe('ReplayControls', () => {
  it('renders without crashing', () => {
    renderReplayControls()
    expect(screen.getByText('Play')).toBeInTheDocument()
  })

  it('shows Play when not playing', () => {
    renderReplayControls({ isPlaying: false })
    expect(screen.getByText('Play')).toBeInTheDocument()
  })

  it('shows Pause when playing', () => {
    renderReplayControls({ isPlaying: true })
    expect(screen.getByText('Pause')).toBeInTheDocument()
  })

  it('calls onTogglePlay when play/pause button clicked', () => {
    const { onTogglePlay } = renderReplayControls()
    fireEvent.click(screen.getByText('Play'))
    expect(onTogglePlay).toHaveBeenCalledTimes(1)
  })

  it('renders all four speed buttons (0.5x, 1x, 2x, 4x)', () => {
    renderReplayControls()
    expect(screen.getByText('0.5x')).toBeInTheDocument()
    expect(screen.getByText('1x')).toBeInTheDocument()
    expect(screen.getByText('2x')).toBeInTheDocument()
    expect(screen.getByText('4x')).toBeInTheDocument()
  })

  it('calls onSpeedChange(2) when 2x is clicked', () => {
    const { onSpeedChange } = renderReplayControls()
    fireEvent.click(screen.getByText('2x'))
    expect(onSpeedChange).toHaveBeenCalledWith(2)
  })

  it('calls onSpeedChange(0.5) when 0.5x is clicked', () => {
    const { onSpeedChange } = renderReplayControls()
    fireEvent.click(screen.getByText('0.5x'))
    expect(onSpeedChange).toHaveBeenCalledWith(0.5)
  })

  it('calls onSpeedChange(4) when 4x is clicked', () => {
    const { onSpeedChange } = renderReplayControls()
    fireEvent.click(screen.getByText('4x'))
    expect(onSpeedChange).toHaveBeenCalledWith(4)
  })

  it('marks the current speed with aria-pressed=true and others false', () => {
    renderReplayControls({ speed: 2 })
    expect(screen.getByText('2x')).toHaveAttribute('aria-pressed', 'true')
    expect(screen.getByText('0.5x')).toHaveAttribute('aria-pressed', 'false')
    expect(screen.getByText('1x')).toHaveAttribute('aria-pressed', 'false')
    expect(screen.getByText('4x')).toHaveAttribute('aria-pressed', 'false')
  })

  it('exposes a group with accessible name for the speed buttons', () => {
    renderReplayControls()
    const group = screen.getByRole('group', { name: /playback speed/i })
    expect(group).toBeInTheDocument()
  })

  it('each speed button has an accessible label', () => {
    renderReplayControls()
    expect(screen.getByLabelText('Playback speed 0.5x')).toBeInTheDocument()
    expect(screen.getByLabelText('Playback speed 1x')).toBeInTheDocument()
    expect(screen.getByLabelText('Playback speed 2x')).toBeInTheDocument()
    expect(screen.getByLabelText('Playback speed 4x')).toBeInTheDocument()
  })

  it('displays current frame / total frames', () => {
    renderReplayControls({ currentFrame: 42, totalFrames: 200 })
    expect(screen.getByText('42 / 200')).toBeInTheDocument()
  })

  it('has a range slider for seeking', () => {
    const { onSeek } = renderReplayControls({ totalFrames: 100 })
    const slider = screen.getByRole('slider')
    expect(slider).toBeInTheDocument()
    fireEvent.change(slider, { target: { value: '50' } })
    expect(onSeek).toHaveBeenCalledWith(50)
  })
})
