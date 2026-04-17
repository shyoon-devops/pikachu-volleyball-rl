import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import type { GameState } from '../../lib/types'

// Stub GameCanvas (PixiJS doesn't render in jsdom cleanly)
vi.mock('../game/GameCanvas', () => ({
  GameCanvas: () => <div data-testid="game-canvas" />,
}))

// Mock getReplay so we can feed a fixed-length frame array.
// `getGames` is also mocked because V4 added a best-effort fetch for
// the bottom metadata strip — without the mock the real fetch path
// runs against undefined and aborts the test load.
const mockGetReplay = vi.fn()
const mockGetGames = vi.fn()
vi.mock('../../lib/api', () => ({
  getReplay: (...args: unknown[]) => mockGetReplay(...args),
  getGames: (...args: unknown[]) => mockGetGames(...args),
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
  // Default the metadata fetch to "no records found" — keyboard tests
  // don't care about the strip, they just need the call to resolve.
  mockGetGames.mockResolvedValueOnce({ data: [], total: 0, page: 1, limit: 100 })
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
    mockGetGames.mockReset()
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
    mockGetGames.mockReset()
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

describe('ReplayPlayer metadata strip (V4, 2026-04-18)', () => {
  beforeEach(() => {
    mockGetReplay.mockReset()
    mockGetGames.mockReset()
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  function makeFrameWithScore(score1: number, score2: number, frame: number): GameState {
    return {
      ball: { x: 0, y: 0, vx: 0, vy: 0, rotation: 0 },
      player1: {
        x: 0, y: 0, vx: 0, vy: 0,
        isJumping: false, isDiving: false, isPowerHitting: false,
      },
      player2: {
        x: 0, y: 0, vx: 0, vy: 0,
        isJumping: false, isDiving: false, isPowerHitting: false,
      },
      score1,
      score2,
      frame,
    }
  }

  it('renders frame-derived final score / winner / duration even without a GameRecord', async () => {
    // /api/games returns empty (game older than page 1) — strip
    // degrades to last-frame derivation only.
    mockGetReplay.mockResolvedValueOnce({
      frames: [
        makeFrameWithScore(0, 0, 0),
        makeFrameWithScore(15, 12, 4500),
      ],
    })
    mockGetGames.mockResolvedValueOnce({ data: [], total: 0, page: 1, limit: 100 })

    render(
      <MemoryRouter initialEntries={['/replay/uuid-orphan']}>
        <Routes>
          <Route path="/replay/:id" element={<ReplayPlayer />} />
        </Routes>
      </MemoryRouter>,
    )

    await waitFor(() => expect(screen.getByLabelText('Replay metadata')).toBeInTheDocument())
    // Final score = last frame, winner derived from score comparison
    // (15 > 12 → P1 wins → "RL Agent"), duration = last frame.frame.
    expect(screen.getByText('RL Agent')).toBeInTheDocument()
    expect(screen.getByText('4500 frames')).toBeInTheDocument()
    // Bot level + rallies fall through to "?" because GameRecord missing.
    expect(screen.getByText('L?')).toBeInTheDocument()
  })

  it('merges GameRecord fields when /api/games resolves a match', async () => {
    mockGetReplay.mockResolvedValueOnce({
      frames: [makeFrameWithScore(15, 14, 5000)],
    })
    mockGetGames.mockResolvedValueOnce({
      data: [{
        id: 'mongo-1',
        gameId: 'uuid-1',
        timestamp: '2026-04-17T17:32:22Z',
        botLevel: 4,
        score1: 15,
        score2: 14,
        winner: 1,
        durationFrames: 5000,
        rallyCount: 7,
        experimentId: 'exp-abc',
      }],
      total: 1,
      page: 1,
      limit: 100,
    })

    render(
      <MemoryRouter initialEntries={['/replay/uuid-1']}>
        <Routes>
          <Route path="/replay/:id" element={<ReplayPlayer />} />
        </Routes>
      </MemoryRouter>,
    )

    await waitFor(() => expect(screen.getByLabelText('Replay metadata')).toBeInTheDocument())
    expect(screen.getByText('L4')).toBeInTheDocument()       // bot level from GameRecord
    expect(screen.getByText('7')).toBeInTheDocument()         // rallies from GameRecord
    expect(screen.getByText('exp-abc')).toBeInTheDocument()   // experiment id
    // KST conversion of 17:32 UTC → 02:32 next day
    expect(screen.getByText(/02:32:22/)).toBeInTheDocument()
  })

  it('keeps the strip rendered when /api/games rejects (degraded mode)', async () => {
    // /games endpoint failure should not blank the strip — frame-derived
    // values still appear.
    mockGetReplay.mockResolvedValueOnce({
      frames: [makeFrameWithScore(8, 15, 3200)],
    })
    mockGetGames.mockRejectedValueOnce(new Error('games endpoint down'))

    render(
      <MemoryRouter initialEntries={['/replay/uuid-x']}>
        <Routes>
          <Route path="/replay/:id" element={<ReplayPlayer />} />
        </Routes>
      </MemoryRouter>,
    )

    await waitFor(() => expect(screen.getByLabelText('Replay metadata')).toBeInTheDocument())
    expect(screen.getByText('Bot')).toBeInTheDocument() // P2 won → "Bot"
    expect(screen.getByText('3200 frames')).toBeInTheDocument()
  })
})
