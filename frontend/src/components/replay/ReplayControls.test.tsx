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

  it('renders speed buttons', () => {
    renderReplayControls()
    expect(screen.getByText('0.5x')).toBeInTheDocument()
    expect(screen.getByText('1x')).toBeInTheDocument()
    expect(screen.getByText('2x')).toBeInTheDocument()
    expect(screen.getByText('4x')).toBeInTheDocument()
  })

  it('calls onSpeedChange when speed button clicked', () => {
    const { onSpeedChange } = renderReplayControls()
    fireEvent.click(screen.getByText('2x'))
    expect(onSpeedChange).toHaveBeenCalledWith(2)
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
