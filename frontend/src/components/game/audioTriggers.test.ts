import { describe, it, expect } from 'vitest'
import { diffAudioTriggers } from './audioTriggers'
import type { GameState } from '../../lib/types'

function makeState(overrides: Partial<GameState> = {}): GameState {
  return {
    player1: {
      x: 100,
      y: 244,
      vx: 0,
      vy: 0,
      isJumping: false,
      isDiving: false,
      isPowerHitting: false,
    },
    player2: {
      x: 332,
      y: 244,
      vx: 0,
      vy: 0,
      isJumping: false,
      isDiving: false,
      isPowerHitting: false,
    },
    ball: { x: 216, y: 200, vx: 0, vy: 0, rotation: 0 },
    score1: 0,
    score2: 0,
    frame: 0,
    ...overrides,
  }
}

describe('diffAudioTriggers', () => {
  it('emits nothing on the very first frame (prev is null)', () => {
    expect(diffAudioTriggers(null, makeState())).toEqual([])
  })

  it('emits powerHit on isPowerHit rising edge', () => {
    const prev = makeState()
    const next = makeState({
      ball: { ...makeState().ball, isPowerHit: true },
    })
    expect(diffAudioTriggers(prev, next)).toEqual([
      { name: 'powerHit', pan: 0 },
    ])
  })

  it('does not emit powerHit while isPowerHit remains true frame-over-frame', () => {
    const prev = makeState({
      ball: { ...makeState().ball, isPowerHit: true },
    })
    const next = makeState({
      ball: { ...makeState().ball, isPowerHit: true },
    })
    expect(diffAudioTriggers(prev, next)).toEqual([])
  })

  it('emits ballTouchesGround on punchEffectRadius rising edge (non-power-hit)', () => {
    const prev = makeState()
    const next = makeState({
      ball: { ...makeState().ball, punchEffectRadius: 20 },
    })
    expect(diffAudioTriggers(prev, next)).toEqual([
      { name: 'ballTouchesGround', pan: 0 },
    ])
  })

  it('suppresses ballTouchesGround when the rising-edge frame is also a power hit', () => {
    // engine.py seeds punch_effect_radius in both branches
    // (439-441 ground, 651-656 power hit). Emit only 'powerHit' here.
    const prev = makeState()
    const next = makeState({
      ball: {
        ...makeState().ball,
        isPowerHit: true,
        punchEffectRadius: 20,
      },
    })
    const events = diffAudioTriggers(prev, next)
    expect(events).toEqual([{ name: 'powerHit', pan: 0 }])
  })

  it('emits pipikachu panned right when P1 scores', () => {
    const prev = makeState({ score1: 3 })
    const next = makeState({ score1: 4 })
    expect(diffAudioTriggers(prev, next)).toEqual([
      { name: 'pipikachu', pan: 1 },
    ])
  })

  it('emits pipikachu panned left when P2 scores', () => {
    const prev = makeState({ score2: 5 })
    const next = makeState({ score2: 6 })
    expect(diffAudioTriggers(prev, next)).toEqual([
      { name: 'pipikachu', pan: -1 },
    ])
  })

  it('handles simultaneous power hit + P1 score in one frame', () => {
    const prev = makeState({ score1: 10 })
    const next = makeState({
      score1: 11,
      ball: { ...makeState().ball, isPowerHit: true },
    })
    expect(diffAudioTriggers(prev, next)).toEqual([
      { name: 'powerHit', pan: 0 },
      { name: 'pipikachu', pan: 1 },
    ])
  })
})
