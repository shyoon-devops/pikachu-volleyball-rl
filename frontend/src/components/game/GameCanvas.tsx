import { useRef, useEffect, useCallback } from 'react'
import { Application, Graphics } from 'pixi.js'
import type { GameState } from '../../lib/types'

const COURT_WIDTH = 432
const COURT_HEIGHT = 304
const NET_X = 216
const NET_TOP_Y = 176
const NET_HALF_WIDTH = 25
const PLAYER_HALF = 32
const BALL_RADIUS = 20
const GROUND_Y = 244

interface GameCanvasProps {
  gameState: GameState | null
  width?: number
  height?: number
}

function lerp(a: number, b: number, t: number): number {
  return a + (b - a) * t
}

function lerpState(prev: GameState, next: GameState, t: number): GameState {
  return {
    player1: {
      x: lerp(prev.player1.x, next.player1.x, t),
      y: lerp(prev.player1.y, next.player1.y, t),
      vx: next.player1.vx,
      vy: next.player1.vy,
      isJumping: next.player1.isJumping,
      isDiving: next.player1.isDiving,
      isPowerHitting: next.player1.isPowerHitting,
    },
    player2: {
      x: lerp(prev.player2.x, next.player2.x, t),
      y: lerp(prev.player2.y, next.player2.y, t),
      vx: next.player2.vx,
      vy: next.player2.vy,
      isJumping: next.player2.isJumping,
      isDiving: next.player2.isDiving,
      isPowerHitting: next.player2.isPowerHitting,
    },
    ball: {
      x: lerp(prev.ball.x, next.ball.x, t),
      y: lerp(prev.ball.y, next.ball.y, t),
      vx: next.ball.vx,
      vy: next.ball.vy,
      rotation: lerp(prev.ball.rotation, next.ball.rotation, t),
    },
    score1: next.score1,
    score2: next.score2,
    frame: next.frame,
  }
}

export function GameCanvas({ gameState, width = COURT_WIDTH, height = COURT_HEIGHT }: GameCanvasProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const appRef = useRef<Application | null>(null)
  const graphicsRef = useRef<Graphics | null>(null)
  const prevStateRef = useRef<GameState | null>(null)
  const currentStateRef = useRef<GameState | null>(null)
  const lerpFactorRef = useRef(0)
  const animFrameRef = useRef(0)

  useEffect(() => {
    const container = containerRef.current
    if (!container) return

    const app = new Application()
    let destroyed = false

    const init = async () => {
      await app.init({
        width: COURT_WIDTH,
        height: COURT_HEIGHT,
        background: 0x1a1a2e,
        antialias: true,
        resolution: window.devicePixelRatio || 1,
        autoDensity: true,
      })

      if (destroyed) {
        app.destroy(true)
        return
      }

      const canvas = app.canvas as HTMLCanvasElement
      canvas.style.width = `${width}px`
      canvas.style.height = `${height}px`
      container.appendChild(canvas)

      const gfx = new Graphics()
      app.stage.addChild(gfx)
      graphicsRef.current = gfx
      appRef.current = app
    }

    init()

    return () => {
      destroyed = true
      if (appRef.current) {
        appRef.current.destroy(true)
        appRef.current = null
      }
      graphicsRef.current = null
    }
  }, [width, height])

  useEffect(() => {
    if (gameState) {
      prevStateRef.current = currentStateRef.current ?? gameState
      currentStateRef.current = gameState
      lerpFactorRef.current = 0
    }
  }, [gameState])

  const drawFrame = useCallback((state: GameState) => {
    const gfx = graphicsRef.current
    if (!gfx) return

    gfx.clear()

    // Sky
    gfx.rect(0, 0, COURT_WIDTH, GROUND_Y)
    gfx.fill(0x87ceeb)

    // Ground
    gfx.rect(0, GROUND_Y, COURT_WIDTH, COURT_HEIGHT - GROUND_Y)
    gfx.fill(0x4a7c59)

    // Net
    gfx.rect(NET_X - NET_HALF_WIDTH / 2, NET_TOP_Y, NET_HALF_WIDTH / 2, GROUND_Y - NET_TOP_Y)
    gfx.fill(0xcccccc)

    // Net top bar
    gfx.rect(NET_X - NET_HALF_WIDTH, NET_TOP_Y - 4, NET_HALF_WIDTH * 2, 4)
    gfx.fill(0xffffff)

    // Player 1 (yellow - left side)
    gfx.circle(state.player1.x, state.player1.y, PLAYER_HALF)
    gfx.fill(0xffd700)
    gfx.circle(state.player1.x, state.player1.y, PLAYER_HALF)
    gfx.stroke({ width: 2, color: 0xb8960f })

    // Player 1 eyes
    gfx.circle(state.player1.x + 8, state.player1.y - 8, 4)
    gfx.fill(0x000000)

    // Player 2 (red - right side)
    gfx.circle(state.player2.x, state.player2.y, PLAYER_HALF)
    gfx.fill(0xff4444)
    gfx.circle(state.player2.x, state.player2.y, PLAYER_HALF)
    gfx.stroke({ width: 2, color: 0xaa2222 })

    // Player 2 eyes
    gfx.circle(state.player2.x - 8, state.player2.y - 8, 4)
    gfx.fill(0x000000)

    // Ball
    gfx.circle(state.ball.x, state.ball.y, BALL_RADIUS)
    gfx.fill(0xffff00)
    gfx.circle(state.ball.x, state.ball.y, BALL_RADIUS)
    gfx.stroke({ width: 2, color: 0xccaa00 })
  }, [])

  useEffect(() => {
    let running = true

    const tick = () => {
      if (!running) return

      const prev = prevStateRef.current
      const next = currentStateRef.current

      if (prev && next) {
        // Interpolate from 30fps server frames to 60fps display
        lerpFactorRef.current = Math.min(lerpFactorRef.current + 1 / 2, 1)
        const interpolated = lerpState(prev, next, lerpFactorRef.current)
        drawFrame(interpolated)
      } else if (next) {
        drawFrame(next)
      }

      animFrameRef.current = requestAnimationFrame(tick)
    }

    animFrameRef.current = requestAnimationFrame(tick)

    return () => {
      running = false
      cancelAnimationFrame(animFrameRef.current)
    }
  }, [drawFrame])

  return <div ref={containerRef} style={{ width, height, position: 'relative' }} />
}
