import type { GameState } from '../../lib/types'
import type { SfxName, Pan } from '../../lib/pikaAudio'

/**
 * Convert a per-frame `sounds` flag map from BE into play events.
 *
 * BE dev 2084a13d emits `sounds.{pipikachu,pika,chu,power_hit,
 * ball_touches_ground}` on every `training:frame`. Each key is true
 * only on the tick the SFX fires — `engine.py:357-364` resets all
 * flags at the start of every tick, so no rising-edge detection is
 * needed on the FE side. We just iterate the flags and emit one
 * event per true entry.
 *
 * We still dispatch against the *server-tick* gameState (not the
 * 60fps interpolated one) so each flag fires exactly once per
 * engine tick — that's the caller's contract, not this helper's.
 *
 * Panning: all five SFX play mono (pan=0). The original audio.js
 * reserved the left / right channels for the menu-layer `pi` and
 * `pikachu` voice cues, which we don't ship. pipikachu's per-side
 * panning used to be FE-derived from score deltas (a heuristic);
 * now that BE owns the trigger, there's no player attribution on
 * the flag, so center-pan is the honest choice.
 */
export interface AudioTriggerEvent {
  name: SfxName
  pan: Pan
}

export function resolveAudioTriggers(state: GameState): AudioTriggerEvent[] {
  const s = state.sounds
  if (!s) return []

  const events: AudioTriggerEvent[] = []
  if (s.powerHit) events.push({ name: 'powerHit', pan: 0 })
  if (s.ballTouchesGround) events.push({ name: 'ballTouchesGround', pan: 0 })
  if (s.pipikachu) events.push({ name: 'pipikachu', pan: 0 })
  if (s.pika) events.push({ name: 'pika', pan: 0 })
  if (s.chu) events.push({ name: 'chu', pan: 0 })
  return events
}
