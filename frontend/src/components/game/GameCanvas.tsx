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
        background: 0x0a1628,
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

    // ── Sky: dark navy gradient feel ──
    gfx.rect(0, 0, COURT_WIDTH, GROUND_Y)
    gfx.fill(0x0f2847)

    // Sky horizon glow
    gfx.rect(0, GROUND_Y - 30, COURT_WIDTH, 30)
    gfx.fill({ color: 0x1a3a5c, alpha: 0.5 })

    // ── Ground: grass with stripe pattern ──
    gfx.rect(0, GROUND_Y, COURT_WIDTH, COURT_HEIGHT - GROUND_Y)
    gfx.fill(0x1b5e20)

    // Grass stripes (alternating shades)
    for (let i = 0; i < 4; i++) {
      const stripeY = GROUND_Y + i * 15
      gfx.rect(0, stripeY, COURT_WIDTH, 7)
      gfx.fill({ color: 0x2e7d32, alpha: 0.4 })
    }

    // Court boundary line
    gfx.rect(0, GROUND_Y, COURT_WIDTH, 2)
    gfx.fill({ color: 0xffffff, alpha: 0.15 })

    // ── Net: grid pattern ──
    const netPostW = 4
    const netLeft = NET_X - netPostW / 2
    const netHeight = GROUND_Y - NET_TOP_Y

    // Net post (dark steel)
    gfx.rect(netLeft, NET_TOP_Y, netPostW, netHeight)
    gfx.fill(0x78909c)
    gfx.rect(netLeft, NET_TOP_Y, netPostW, netHeight)
    gfx.stroke({ width: 1, color: 0x90a4ae })

    // Net top bar
    gfx.rect(NET_X - NET_HALF_WIDTH, NET_TOP_Y - 3, NET_HALF_WIDTH * 2, 3)
    gfx.fill(0xb0bec5)

    // Net mesh (horizontal lines)
    for (let y = NET_TOP_Y + 8; y < GROUND_Y; y += 8) {
      gfx.moveTo(NET_X - NET_HALF_WIDTH + 2, y)
      gfx.lineTo(NET_X + NET_HALF_WIDTH - 2, y)
      gfx.stroke({ width: 1, color: 0x546e7a, alpha: 0.6 })
    }

    // Net mesh (vertical lines)
    for (let x = NET_X - NET_HALF_WIDTH + 6; x < NET_X + NET_HALF_WIDTH; x += 6) {
      gfx.moveTo(x, NET_TOP_Y)
      gfx.lineTo(x, GROUND_Y)
      gfx.stroke({ width: 1, color: 0x546e7a, alpha: 0.4 })
    }

    // ── Player 1 (Pikachu Yellow — left side) ──
    drawPlayer(gfx, state.player1.x, state.player1.y, 0xffd700, 0xb8960f, true, state.player1.isPowerHitting)

    // ── Player 2 (Electric Blue — right side) ──
    drawPlayer(gfx, state.player2.x, state.player2.y, 0x4fc3f7, 0x2196f3, false, state.player2.isPowerHitting)

    // ── Ball ──
    drawBall(gfx, state.ball.x, state.ball.y, state.ball.rotation)
  }, [])

  useEffect(() => {
    let running = true

    const tick = () => {
      if (!running) return

      const prev = prevStateRef.current
      const next = currentStateRef.current

      if (prev && next) {
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

  return (
    <div
      ref={containerRef}
      style={{
        width,
        height,
        position: 'relative',
        borderRadius: 'var(--radius-lg)',
        overflow: 'hidden',
        border: '2px solid var(--color-border-strong)',
        boxShadow: '0 0 30px rgba(0, 0, 0, 0.5), inset 0 0 60px rgba(0, 0, 0, 0.2)',
      }}
    />
  )
}

function drawPlayer(
  gfx: Graphics,
  x: number,
  y: number,
  bodyColor: number,
  borderColor: number,
  facingRight: boolean,
  isPowerHitting: boolean,
) {
  const halfW = PLAYER_HALF * 0.75
  const halfH = PLAYER_HALF

  // Shadow on ground
  if (y < GROUND_Y) {
    const shadowScale = 1 - (GROUND_Y - y) / 200
    gfx.ellipse(x, GROUND_Y + 4, halfW * Math.max(0.3, shadowScale), 4)
    gfx.fill({ color: 0x000000, alpha: 0.2 })
  }

  // Body: rounded rectangle (pikachu-like)
  gfx.roundRect(x - halfW, y - halfH, halfW * 2, halfH * 2, 12)
  gfx.fill(bodyColor)
  gfx.roundRect(x - halfW, y - halfH, halfW * 2, halfH * 2, 12)
  gfx.stroke({ width: 2, color: borderColor })

  // Power hit glow
  if (isPowerHitting) {
    gfx.circle(x, y, PLAYER_HALF + 6)
    gfx.stroke({ width: 2, color: 0xffeb3b, alpha: 0.5 })
  }

  // Belly highlight
  gfx.ellipse(x, y + 6, halfW * 0.55, halfH * 0.45)
  gfx.fill({ color: 0xffffff, alpha: 0.12 })

  // Eyes
  const eyeDir = facingRight ? 1 : -1
  const eyeX = x + eyeDir * 7
  const eyeY = y - 10

  // Eye whites
  gfx.ellipse(eyeX, eyeY, 5, 6)
  gfx.fill(0xffffff)

  // Pupils
  gfx.circle(eyeX + eyeDir * 1.5, eyeY, 2.5)
  gfx.fill(0x1a1a2e)

  // Eye shine
  gfx.circle(eyeX + eyeDir * 3, eyeY - 2, 1.2)
  gfx.fill(0xffffff)

  // Cheek blush (pikachu red cheeks)
  const cheekX = x + eyeDir * 14
  gfx.circle(cheekX, y - 2, 5)
  gfx.fill({ color: 0xff6b6b, alpha: 0.35 })

  // Ears (small triangular bumps)
  const earX = x + eyeDir * 6
  gfx.moveTo(earX - 4, y - halfH)
  gfx.lineTo(earX, y - halfH - 10)
  gfx.lineTo(earX + 4, y - halfH)
  gfx.fill(bodyColor)

  // Ear tip
  gfx.moveTo(earX - 2, y - halfH - 3)
  gfx.lineTo(earX, y - halfH - 10)
  gfx.lineTo(earX + 2, y - halfH - 3)
  gfx.fill(borderColor)
}

function drawBall(gfx: Graphics, x: number, y: number, _rotation: number) {
  // Ball shadow on ground
  if (y < GROUND_Y) {
    const shadowScale = 1 - (GROUND_Y - y) / 300
    gfx.ellipse(x, GROUND_Y + 3, BALL_RADIUS * 0.6 * Math.max(0.2, shadowScale), 3)
    gfx.fill({ color: 0x000000, alpha: 0.15 })
  }

  // Ball outer glow
  gfx.circle(x, y, BALL_RADIUS + 3)
  gfx.fill({ color: 0xffeb3b, alpha: 0.15 })

  // Ball body
  gfx.circle(x, y, BALL_RADIUS)
  gfx.fill(0xffeb3b)
  gfx.circle(x, y, BALL_RADIUS)
  gfx.stroke({ width: 2, color: 0xf9a825 })

  // Ball highlight (top-left shine)
  gfx.circle(x - 5, y - 5, BALL_RADIUS * 0.35)
  gfx.fill({ color: 0xffffff, alpha: 0.4 })

  // Ball line (volleyball seam)
  gfx.moveTo(x - BALL_RADIUS + 4, y)
  gfx.lineTo(x + BALL_RADIUS - 4, y)
  gfx.stroke({ width: 1, color: 0xf9a825, alpha: 0.5 })

  // Vertical seam
  gfx.moveTo(x, y - BALL_RADIUS + 4)
  gfx.lineTo(x, y + BALL_RADIUS - 4)
  gfx.stroke({ width: 1, color: 0xf9a825, alpha: 0.3 })
}
