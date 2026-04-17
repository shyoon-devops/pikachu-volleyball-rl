import type { GameState } from '../../lib/types'
import type { SfxName, Pan } from '../../lib/pikaAudio'

/**
 * Derive audio triggers from a pair of consecutive WS game frames.
 *
 * The BE currently emits two relevant flags per frame — `is_power_hit`
 * and `punch_effect_radius` — plus score1 / score2 / frame counters.
 * It does NOT emit the original engine's `sound_*` booleans
 * (`engine.py:437, 659`), so the FE has to detect transitions itself.
 *
 * Ruleset (aligns with audio.js + pikavolley.js trigger points):
 *
 *   - `ball.isPowerHit` rising edge      → 'powerHit' (center)
 *   - score1 incremented                 → 'pipikachu' (right — P1 side)
 *   - score2 incremented                 → 'pipikachu' (left  — P2 side)
 *   - `punchEffectRadius` rising edge
 *     AND NOT isPowerHit                 → 'ballTouchesGround' (center)
 *
 * The pikachu voice SFX (pi / pika / chu / pikachu) are reserved but
 * not triggered by any currently-observable state. When BE starts
 * emitting per-frame voice flags we'll extend this helper without
 * touching GameCanvas.
 *
 * Pure function; returns an array so the caller can dispatch them to
 * the audio singleton in order. Tested without a DOM or WebAudio
 * context — keeps the GameCanvas.tsx integration simple.
 */
export interface AudioTriggerEvent {
  name: SfxName
  pan: Pan
}

export function diffAudioTriggers(
  prev: GameState | null,
  next: GameState,
): AudioTriggerEvent[] {
  const events: AudioTriggerEvent[] = []
  if (!prev) return events

  const prevIsPowerHit = prev.ball.isPowerHit === true
  const nextIsPowerHit = next.ball.isPowerHit === true
  if (nextIsPowerHit && !prevIsPowerHit) {
    events.push({ name: 'powerHit', pan: 0 })
  }

  const prevRadius = prev.ball.punchEffectRadius ?? 0
  const nextRadius = next.ball.punchEffectRadius ?? 0
  const radiusRising = nextRadius > 0 && prevRadius === 0
  // `punch_effect_radius` is seeded by BOTH the power-hit branch and
  // the ball-ground-touch branch (engine.py:439-441, 651-656). When a
  // power hit is firing this frame we've already queued 'powerHit';
  // suppress the ground sound to avoid double playback.
  if (radiusRising && !nextIsPowerHit) {
    events.push({ name: 'ballTouchesGround', pan: 0 })
  }

  if (next.score1 > prev.score1) {
    events.push({ name: 'pipikachu', pan: 1 })
  }
  if (next.score2 > prev.score2) {
    events.push({ name: 'pipikachu', pan: -1 })
  }

  return events
}
