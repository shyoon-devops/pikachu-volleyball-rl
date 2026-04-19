import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, act } from '@testing-library/react'
import { UpdatingOverlay } from './UpdatingOverlay'

describe('UpdatingOverlay (spec f02a9785)', () => {
  beforeEach(() => {
    vi.useFakeTimers({ shouldAdvanceTime: false })
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('renders nothing when show is false from the start', () => {
    const { container } = render(<UpdatingOverlay show={false} />)
    expect(container.querySelector('.updating-overlay')).toBeNull()
  })

  it('mounts with role="status" + spec copy when show flips to true', () => {
    render(<UpdatingOverlay show={true} />)
    const overlay = screen.getByRole('status', { name: /Updating training policy/i })
    expect(overlay).toBeInTheDocument()
    expect(screen.getByText('Updating policy')).toBeInTheDocument()
    expect(screen.getByText('PPO gradient update in progress')).toBeInTheDocument()
  })

  it('shows the long-gap subtitle when longGap prop is true', () => {
    render(<UpdatingOverlay show={true} longGap={true} />)
    expect(screen.getByText('This is taking longer than usual…')).toBeInTheDocument()
    expect(screen.queryByText('PPO gradient update in progress')).toBeNull()
  })

  it('enforces the 400 ms minimum-visible floor (spec §2)', () => {
    const { rerender, container } = render(<UpdatingOverlay show={true} />)
    // Drop the flag 100 ms after show → fade-out must be delayed
    // another 300 ms to honour the 400 ms floor.
    act(() => { vi.advanceTimersByTime(100) })
    rerender(<UpdatingOverlay show={false} />)

    // 100 ms after the prop flip — still fully visible because the
    // startHide timeout hasn't fired yet.
    act(() => { vi.advanceTimersByTime(100) })
    expect(container.querySelector('.updating-overlay--visible')).not.toBeNull()

    // Another 200 ms — now ≥ 400 ms since show; fade-out starts.
    act(() => { vi.advanceTimersByTime(200) })
    expect(container.querySelector('.updating-overlay--visible')).toBeNull()
    expect(container.querySelector('.updating-overlay')).not.toBeNull()

    // Fade-out window (300 ms) — node unmounts.
    act(() => { vi.advanceTimersByTime(300) })
    expect(container.querySelector('.updating-overlay')).toBeNull()
  })

  it('starts fade-out immediately when the minimum-visible floor already elapsed', () => {
    const { rerender, container } = render(<UpdatingOverlay show={true} />)
    // Sit visible for 500 ms, past the 400 ms floor.
    act(() => { vi.advanceTimersByTime(500) })
    rerender(<UpdatingOverlay show={false} />)
    // No delay — visible class removed on the same tick.
    act(() => { vi.advanceTimersByTime(0) })
    expect(container.querySelector('.updating-overlay--visible')).toBeNull()
  })

  it('cancels a pending fade-out if show flips back to true mid-delay', () => {
    const { rerender, container } = render(<UpdatingOverlay show={true} />)
    act(() => { vi.advanceTimersByTime(100) }) // inside 400 ms floor
    rerender(<UpdatingOverlay show={false} />)
    // Within 300 ms of the flip, show recovers → the pending hide
    // timer should be cancelled and the overlay stays visible.
    act(() => { vi.advanceTimersByTime(150) })
    rerender(<UpdatingOverlay show={true} />)
    act(() => { vi.advanceTimersByTime(500) })
    expect(container.querySelector('.updating-overlay--visible')).not.toBeNull()
  })
})
