import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { BatchTabBar } from './BatchTabBar'
import type { EnvFramesMap } from '../../hooks/useTrainingState'
import type { GameState, EnvFramePayload } from '../../lib/types'

// Minimal game-state stub — BatchTabBar only reads score off the
// payload's top-level `score` array, so the inner frame can be a
// partial cast. Kept as a helper so each test composes the shape
// it cares about without repeating boilerplate.
function envPayload(
  envId: number,
  score: [number, number],
  stateName = 'round',
): EnvFramePayload {
  return {
    envId,
    score,
    stateName,
    step: 1000,
    frame: {
      player1: { x: 0, y: 0, vx: 0, vy: 0, isJumping: false, isDiving: false, isPowerHitting: false },
      player2: { x: 0, y: 0, vx: 0, vy: 0, isJumping: false, isDiving: false, isPowerHitting: false },
      ball: { x: 0, y: 0, vx: 0, vy: 0, rotation: 0 },
      score1: score[0],
      score2: score[1],
      frame: 0,
    } as GameState,
  }
}

function envMap(...pairs: EnvFramePayload[]): EnvFramesMap {
  const out: EnvFramesMap = {}
  for (const p of pairs) out[p.envId] = p
  return out
}

describe('BatchTabBar', () => {
  beforeEach(() => {
    vi.useRealTimers()
  })
  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('renders nEnvs chips (ENV 0..N-1) with live scores', () => {
    render(
      <BatchTabBar
        envFrames={envMap(envPayload(0, [3, 5]), envPayload(1, [7, 2]))}
        nEnvs={2}
        activeEnvId={0}
        onSelect={vi.fn()}
      />,
    )
    const tabs = screen.getAllByRole('tab')
    expect(tabs).toHaveLength(2)
    expect(tabs[0]).toHaveTextContent('ENV 0')
    expect(tabs[0]).toHaveTextContent('3')
    expect(tabs[0]).toHaveTextContent('5')
    expect(tabs[1]).toHaveTextContent('ENV 1')
    expect(tabs[1]).toHaveTextContent('7')
    expect(tabs[1]).toHaveTextContent('2')
  })

  it('renders 0:0 for envs that have not broadcast yet', () => {
    // nEnvs=4 but only env 0 has a frame → 1..3 show a score fallback
    // so the bar doesn't look broken during the first seconds of a run.
    render(
      <BatchTabBar
        envFrames={envMap(envPayload(0, [1, 2]))}
        nEnvs={4}
        activeEnvId={0}
        onSelect={vi.fn()}
      />,
    )
    const tabs = screen.getAllByRole('tab')
    expect(tabs).toHaveLength(4)
    expect(tabs[1].textContent).toMatch(/ENV 1.*0.*0/)
  })

  it('marks the active tab with aria-selected + the --active className', () => {
    render(
      <BatchTabBar
        envFrames={envMap(envPayload(0, [0, 0]), envPayload(1, [0, 0]))}
        nEnvs={2}
        activeEnvId={1}
        onSelect={vi.fn()}
      />,
    )
    const tabs = screen.getAllByRole('tab')
    expect(tabs[0]).toHaveAttribute('aria-selected', 'false')
    expect(tabs[1]).toHaveAttribute('aria-selected', 'true')
    expect(tabs[1].className).toContain('batch-tab--active')
  })

  it('fires onSelect when a chip is clicked', () => {
    const onSelect = vi.fn()
    render(
      <BatchTabBar
        envFrames={envMap(envPayload(0, [0, 0]), envPayload(1, [0, 0]))}
        nEnvs={2}
        activeEnvId={0}
        onSelect={onSelect}
      />,
    )
    fireEvent.click(screen.getAllByRole('tab')[1])
    expect(onSelect).toHaveBeenCalledWith(1)
  })

  it('cycles via ← / → keyboard', () => {
    const onSelect = vi.fn()
    render(
      <BatchTabBar
        envFrames={envMap(envPayload(0, [0, 0]))}
        nEnvs={4}
        activeEnvId={0}
        onSelect={onSelect}
      />,
    )
    fireEvent.keyDown(window, { code: 'ArrowRight' })
    expect(onSelect).toHaveBeenLastCalledWith(1)
    // Wraps around from 0 → 3 with ArrowLeft.
    fireEvent.keyDown(window, { code: 'ArrowLeft' })
    expect(onSelect).toHaveBeenLastCalledWith(3)
  })

  it('jumps via digit keys 1..8 to ENV 0..7', () => {
    const onSelect = vi.fn()
    render(
      <BatchTabBar
        envFrames={envMap(envPayload(0, [0, 0]))}
        nEnvs={8}
        activeEnvId={0}
        onSelect={onSelect}
      />,
    )
    fireEvent.keyDown(window, { code: 'Digit3' })
    expect(onSelect).toHaveBeenLastCalledWith(2)
    fireEvent.keyDown(window, { code: 'Digit8' })
    expect(onSelect).toHaveBeenLastCalledWith(7)
  })

  it('ignores digit keys that would address an env past nEnvs', () => {
    const onSelect = vi.fn()
    render(
      <BatchTabBar
        envFrames={envMap(envPayload(0, [0, 0]))}
        nEnvs={3}
        activeEnvId={0}
        onSelect={onSelect}
      />,
    )
    fireEvent.keyDown(window, { code: 'Digit5' }) // → ENV 4, out of range
    expect(onSelect).not.toHaveBeenCalled()
  })

  it('renders the danger dot when stateName is gameEnd', () => {
    const { container } = render(
      <BatchTabBar
        envFrames={envMap(envPayload(0, [15, 14], 'gameEnd'))}
        nEnvs={1}
        activeEnvId={0}
        onSelect={vi.fn()}
      />,
    )
    const dot = container.querySelector('.batch-tab-dot')
    expect(dot?.className).toContain('batch-tab-dot--danger')
  })

  it('renders a warning-pulse dot for live/round state', () => {
    const { container } = render(
      <BatchTabBar
        envFrames={envMap(envPayload(0, [3, 2], 'round'))}
        nEnvs={1}
        activeEnvId={0}
        onSelect={vi.fn()}
      />,
    )
    const dot = container.querySelector('.batch-tab-dot')
    expect(dot?.className).toContain('batch-tab-dot--warning')
  })

  it('switches ≥9 envs to scroll-snap layout (spec §5)', () => {
    const { container } = render(
      <BatchTabBar
        envFrames={{}}
        nEnvs={12}
        activeEnvId={0}
        onSelect={vi.fn()}
      />,
    )
    const bar = container.querySelector('.batch-tab-bar')
    expect(bar?.getAttribute('data-overflow')).toBe('scroll')
  })

  it('uses grid layout for ≤8 envs', () => {
    const { container } = render(
      <BatchTabBar
        envFrames={{}}
        nEnvs={8}
        activeEnvId={0}
        onSelect={vi.fn()}
      />,
    )
    const bar = container.querySelector('.batch-tab-bar')
    expect(bar?.getAttribute('data-overflow')).toBe('grid')
  })
})
