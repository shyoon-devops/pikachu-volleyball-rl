import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import type { GameState } from '../../lib/types'

// Stub GameCanvas (PixiJS doesn't render in jsdom cleanly)
vi.mock('../game/GameCanvas', () => ({
  GameCanvas: () => <div data-testid="game-canvas" />,
}))

// Mock getReplay so we can feed a fixed-length frame array
const mockGetReplay = vi.fn()
vi.mock('../../lib/api', () => ({
  getReplay: (...args: unknown[]) => mockGetReplay(...args),
}))

import { ReplayPlayer } from './ReplayPlayer'

function makeFrames(count: number): GameState[] {
  return Array.from({ length: count }, () => ({
    ball: { x: 0, y: 0, vx: 0, vy: 0 },
    p1: { x: 0, y: 0, vx: 0, vy: 0, diving: false, stunned: false },
    p2: { x: 0, y: 0, vx: 0, vy: 0, diving: false, stunned: false },
    score1: 0,
    score2: 0,
  } as unknown as GameState))
}

async function renderPlayerWithFrames(count: number) {
  mockGetReplay.mockResolvedValueOnce({ frames: makeFrames(count) })
  render(
    <MemoryRouter initialEntries={['/replay/game-1']}>
      <Routes>
        <Route path="/replay/:id" element={<ReplayPlayer />} />
      </Routes>
    </MemoryRouter>,
  )
  // wait for the controls to appear after the replay loads
  await waitFor(() => {
    expect(screen.getByRole('slider')).toBeInTheDocument()
  })
}

function frameCounterText() {
  // "<current> / <total>" lives in replay-controls-frame-info
  const info = document.querySelector('.replay-controls-frame-info')
  return info?.textContent ?? ''
}

describe('ReplayPlayer keyboard scrubbing', () => {
  beforeEach(() => {
    mockGetReplay.mockReset()
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('ArrowRight advances exactly one frame', async () => {
    await renderPlayerWithFrames(50)
    expect(frameCounterText()).toContain('0 / 50')
    fireEvent.keyDown(window, { code: 'ArrowRight' })
    expect(frameCounterText()).toContain('1 / 50')
  })

  it('ArrowLeft rewinds one frame but clamps at 0', async () => {
    await renderPlayerWithFrames(50)
    fireEvent.keyDown(window, { code: 'ArrowRight' })
    fireEvent.keyDown(window, { code: 'ArrowRight' })
    expect(frameCounterText()).toContain('2 / 50')
    fireEvent.keyDown(window, { code: 'ArrowLeft' })
    expect(frameCounterText()).toContain('1 / 50')
    fireEvent.keyDown(window, { code: 'ArrowLeft' })
    fireEvent.keyDown(window, { code: 'ArrowLeft' })
    expect(frameCounterText()).toContain('0 / 50')
  })

  it('ArrowUp jumps +10 frames', async () => {
    await renderPlayerWithFrames(50)
    fireEvent.keyDown(window, { code: 'ArrowUp' })
    expect(frameCounterText()).toContain('10 / 50')
    fireEvent.keyDown(window, { code: 'ArrowUp' })
    expect(frameCounterText()).toContain('20 / 50')
  })

  it('ArrowDown jumps -10 frames and clamps', async () => {
    await renderPlayerWithFrames(50)
    fireEvent.keyDown(window, { code: 'ArrowUp' })
    fireEvent.keyDown(window, { code: 'ArrowUp' })
    expect(frameCounterText()).toContain('20 / 50')
    fireEvent.keyDown(window, { code: 'ArrowDown' })
    expect(frameCounterText()).toContain('10 / 50')
    // Clamp at 0
    fireEvent.keyDown(window, { code: 'ArrowDown' })
    fireEvent.keyDown(window, { code: 'ArrowDown' })
    expect(frameCounterText()).toContain('0 / 50')
  })

  it('Home jumps to first frame, End jumps to last', async () => {
    await renderPlayerWithFrames(50)
    fireEvent.keyDown(window, { code: 'End' })
    expect(frameCounterText()).toContain('49 / 50')
    fireEvent.keyDown(window, { code: 'Home' })
    expect(frameCounterText()).toContain('0 / 50')
  })

  it('stepping clamps at the final frame without going past', async () => {
    await renderPlayerWithFrames(5)
    fireEvent.keyDown(window, { code: 'End' })
    expect(frameCounterText()).toContain('4 / 5')
    fireEvent.keyDown(window, { code: 'ArrowRight' })
    expect(frameCounterText()).toContain('4 / 5')
    fireEvent.keyDown(window, { code: 'ArrowUp' })
    expect(frameCounterText()).toContain('4 / 5')
  })

  it('ignores keyboard input while typing in an input field', async () => {
    await renderPlayerWithFrames(50)
    // The seek slider is an <input type="range">. Firing a keydown
    // with the slider as target should be ignored by our handler.
    const slider = screen.getByRole('slider') as HTMLInputElement
    slider.focus()
    fireEvent.keyDown(slider, { code: 'ArrowRight' })
    expect(frameCounterText()).toContain('0 / 50')
  })
})

describe('ReplayControls shortcuts hint', () => {
  beforeEach(() => {
    mockGetReplay.mockReset()
  })

  it('documents the ←/→ and ↓/↑ keyboard shortcuts', async () => {
    await renderPlayerWithFrames(10)
    const hint = document.querySelector('.replay-controls-shortcuts')
    expect(hint).not.toBeNull()
    const text = hint!.textContent ?? ''
    expect(text).toMatch(/1 frame/i)
    expect(text).toMatch(/10 frames/i)
  })
})
