import { describe, it, expect } from 'vitest'
import { resolveAudioTriggers } from './audioTriggers'
import type { GameState } from '../../lib/types'

function makeState(sounds?: GameState['sounds']): GameState {
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
    sounds,
  }
}

describe('resolveAudioTriggers', () => {
  it('returns [] when sounds payload is absent (pre-port replay)', () => {
    expect(resolveAudioTriggers(makeState())).toEqual([])
  })

  it('returns [] when every flag is false', () => {
    expect(
      resolveAudioTriggers(
        makeState({
          pipikachu: false,
          pika: false,
          chu: false,
          powerHit: false,
          ballTouchesGround: false,
        }),
      ),
    ).toEqual([])
  })

  it('emits powerHit when sounds.powerHit is true', () => {
    expect(resolveAudioTriggers(makeState({ powerHit: true }))).toEqual([
      { name: 'powerHit', pan: 0 },
    ])
  })

  it('emits ballTouchesGround when sounds.ballTouchesGround is true', () => {
    expect(
      resolveAudioTriggers(makeState({ ballTouchesGround: true })),
    ).toEqual([{ name: 'ballTouchesGround', pan: 0 }])
  })

  it('emits the 3 pikachu-voice SFX (pipikachu / pika / chu) independently', () => {
    expect(resolveAudioTriggers(makeState({ pipikachu: true }))).toEqual([
      { name: 'pipikachu', pan: 0 },
    ])
    expect(resolveAudioTriggers(makeState({ pika: true }))).toEqual([
      { name: 'pika', pan: 0 },
    ])
    expect(resolveAudioTriggers(makeState({ chu: true }))).toEqual([
      { name: 'chu', pan: 0 },
    ])
  })

  it('emits all 5 events on a frame where every flag is true (stable order)', () => {
    // Physically unlikely but locks in emission order so downstream
    // play() invocations stay stable across refactors.
    const events = resolveAudioTriggers(
      makeState({
        pipikachu: true,
        pika: true,
        chu: true,
        powerHit: true,
        ballTouchesGround: true,
      }),
    )
    expect(events.map((e) => e.name)).toEqual([
      'powerHit',
      'ballTouchesGround',
      'pipikachu',
      'pika',
      'chu',
    ])
  })

  it('all events center-pan (pi / pikachu menu sounds are out of scope)', () => {
    const events = resolveAudioTriggers(
      makeState({
        pipikachu: true,
        pika: true,
        chu: true,
        powerHit: true,
        ballTouchesGround: true,
      }),
    )
    expect(events.every((e) => e.pan === 0)).toBe(true)
  })
})
