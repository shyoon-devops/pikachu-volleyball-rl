import { useMemo } from 'react'
import { useSearchParams } from 'react-router-dom'
import { GameCanvas } from './GameCanvas'
import type { GameState } from '../../lib/types'

/**
 * Visual regression harness. Renders `<GameCanvas>` with a fixed
 * `gameState` selected by the `?scene=` query parameter.
 *
 * This page exists so visual regression tests (Playwright) can capture
 * deterministic screenshots without depending on a running backend or
 * a live WebSocket — the scenes below cover the four high-signal
 * moments the original renderer is expected to match:
 *
 *   ?scene=serve     — initial serve position, score 0-0
 *   ?scene=rally     — mid-air rally, no SFX
 *   ?scene=powerhit  — power-hit frame (trail + hyper + ring active)
 *   ?scene=gameend   — 15-14 final score, gameEnd overlay frame 10
 *
 * The harness is intentionally decoupled from `TrainingStateProvider`
 * — it passes a literal `gameState` prop, so the global WS hook still
 * attempts to connect in the background but has no effect on what the
 * canvas draws. Keeping it route-only (not a separate entry HTML file)
 * means the production bundle only carries it once, and the route is
 * discoverable via the React Router registry.
 */

const SCENES = {
  serve: (): GameState => ({
    player1: {
      x: 100,
      y: 244,
      vx: 0,
      vy: 0,
      isJumping: false,
      isDiving: false,
      isPowerHitting: false,
      state: 0,
      frameNumber: 0,
    },
    player2: {
      x: 332,
      y: 244,
      vx: 0,
      vy: 0,
      isJumping: false,
      isDiving: false,
      isPowerHitting: false,
      state: 0,
      frameNumber: 0,
    },
    ball: { x: 100, y: 100, vx: 0, vy: 0, rotation: 0 },
    score1: 0,
    score2: 0,
    frame: 0,
  }),
  rally: (): GameState => ({
    player1: {
      x: 140,
      y: 200,
      vx: 3,
      vy: -7,
      isJumping: true,
      isDiving: false,
      isPowerHitting: false,
      state: 1,
      frameNumber: 2,
    },
    player2: {
      x: 300,
      y: 220,
      vx: -2,
      vy: -4,
      isJumping: true,
      isDiving: false,
      isPowerHitting: false,
      state: 1,
      frameNumber: 3,
    },
    ball: { x: 216, y: 150, vx: 5, vy: -3, rotation: 2 },
    score1: 3,
    score2: 5,
    frame: 420,
  }),
  powerhit: (): GameState => ({
    player1: {
      x: 160,
      y: 180,
      vx: 4,
      vy: -8,
      isJumping: true,
      isDiving: false,
      isPowerHitting: true,
      state: 2,
      frameNumber: 0,
    },
    player2: {
      x: 300,
      y: 240,
      vx: 0,
      vy: 0,
      isJumping: false,
      isDiving: false,
      isPowerHitting: false,
      state: 0,
      frameNumber: 0,
    },
    ball: {
      x: 200,
      y: 160,
      vx: 20,
      vy: -4,
      rotation: 3,
      isPowerHit: true,
      previousX: 180,
      previousY: 170,
      previousPreviousX: 165,
      previousPreviousY: 180,
      punchEffectX: 180,
      punchEffectY: 170,
      punchEffectRadius: 16,
    },
    score1: 8,
    score2: 7,
    frame: 612,
  }),
  gameend: (): GameState => ({
    player1: {
      x: 100,
      y: 244,
      vx: 0,
      vy: 0,
      isJumping: false,
      isDiving: false,
      isPowerHitting: false,
      // state 5 = winning pose (frameForState 5,0 → sprite index 18)
      state: 5,
      frameNumber: 0,
    },
    player2: {
      x: 332,
      y: 244,
      vx: 0,
      vy: 0,
      isJumping: false,
      isDiving: false,
      isPowerHitting: false,
      // state 6 = losing pose (frameForState 6,0 → sprite index 23)
      state: 6,
      frameNumber: 0,
    },
    ball: { x: 216, y: 200, vx: 0, vy: 0, rotation: 0 },
    score1: 15,
    score2: 14,
    frame: 9999,
    isRoundOver: true,
    isGameEnded: true,
    // frame 10 of the 50-frame intro — overlay still mid-animation so
    // the snapshot catches the expanding phase rather than the static
    // hold that lasts most of the window.
    gameEndFrameCounter: 10,
  }),
}

type SceneName = keyof typeof SCENES

function parseScene(raw: string | null): SceneName {
  if (raw === 'rally' || raw === 'powerhit' || raw === 'gameend') return raw
  return 'serve'
}

export function VisualHarness() {
  const [params] = useSearchParams()
  const scene = parseScene(params.get('scene'))
  const state = useMemo(() => SCENES[scene](), [scene])

  return (
    <div style={{ padding: 24, background: '#111' }} data-testid="visual-harness" data-scene={scene}>
      <GameCanvas gameState={state} width={432} height={304} />
    </div>
  )
}
