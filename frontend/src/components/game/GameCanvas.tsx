import { useRef, useEffect, useCallback } from 'react'
import {
  Application,
  Graphics,
  Container,
  Assets,
  Spritesheet,
  Sprite,
  AnimatedSprite,
  Texture,
} from 'pixi.js'
import type { GameState } from '../../lib/types'
import './GameCanvas.css'

const COURT_WIDTH = 432
const COURT_HEIGHT = 304
const NET_X = 216
const NET_TOP_Y = 176
const NET_HALF_WIDTH = 25
const PLAYER_HALF = 32
const BALL_RADIUS = 20
const GROUND_Y = 244
const SHADOW_Y = 273

const SPRITE_SHEET_PATH = '/assets/sprite_sheet.json'

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
      isJumping: next.player1.isJumping ?? false,
      isDiving: next.player1.isDiving ?? false,
      isPowerHitting: next.player1.isPowerHitting ?? false,
    },
    player2: {
      x: lerp(prev.player2.x, next.player2.x, t),
      y: lerp(prev.player2.y, next.player2.y, t),
      vx: next.player2.vx,
      vy: next.player2.vy,
      isJumping: next.player2.isJumping ?? false,
      isDiving: next.player2.isDiving ?? false,
      isPowerHitting: next.player2.isPowerHitting ?? false,
    },
    ball: {
      x: lerp(prev.ball.x, next.ball.x, t),
      y: lerp(prev.ball.y, next.ball.y, t),
      vx: next.ball.vx,
      vy: next.ball.vy,
      rotation: lerp(prev.ball.rotation ?? 0, next.ball.rotation ?? 0, t),
    },
    score1: next.score1,
    score2: next.score2,
    frame: next.frame,
  }
}

/** Infer pikachu animation frame index from velocity (backend doesn't send state/frameNumber). */
function inferPlayerFrame(vx: number, vy: number, frameCounter: number): number {
  if (vy !== 0) {
    // Jump: state=2, 5 frames (indices 10-14)
    return 10 + (frameCounter % 5)
  }
  if (Math.abs(vx) > 0) {
    // Walk: state=1, 5 frames (indices 5-9)
    return 5 + (frameCounter % 5)
  }
  // Idle: state=0, 5 frames (indices 0-4)
  return frameCounter % 5
}

/** Build the ordered texture array for pikachu AnimatedSprite (28 frames total). */
function buildPlayerTextures(textures: Record<string, Texture>): Texture[] {
  const result: Texture[] = []
  for (let i = 0; i < 7; i++) {
    if (i === 3) {
      result.push(textures[`pikachu/pikachu_3_0.png`])
      result.push(textures[`pikachu/pikachu_3_1.png`])
    } else if (i === 4) {
      result.push(textures[`pikachu/pikachu_4_0.png`])
    } else {
      for (let j = 0; j < 5; j++) {
        result.push(textures[`pikachu/pikachu_${i}_${j}.png`])
      }
    }
  }
  return result
}

function buildBallTextures(textures: Record<string, Texture>): Texture[] {
  return [
    textures['ball/ball_0.png'],
    textures['ball/ball_1.png'],
    textures['ball/ball_2.png'],
    textures['ball/ball_3.png'],
    textures['ball/ball_4.png'],
    textures['ball/ball_hyper.png'],
  ]
}

interface SpriteObjects {
  bg: Container
  player1: AnimatedSprite
  player2: AnimatedSprite
  ball: AnimatedSprite
  shadowP1: Sprite
  shadowP2: Sprite
  shadowBall: Sprite
}

function buildSpriteScene(
  textures: Record<string, Texture>,
  stage: Container,
): SpriteObjects {
  // Background
  const bg = new Container()

  // Sky (tiled 16x16)
  const skyTex = textures['objects/sky_blue.png']
  for (let y = 0; y < GROUND_Y; y += 16) {
    for (let x = 0; x < COURT_WIDTH; x += 16) {
      const tile = new Sprite(skyTex)
      tile.x = x
      tile.y = y
      bg.addChild(tile)
    }
  }

  // Mountain
  const mountainTex = textures['objects/mountain.png']
  if (mountainTex) {
    const mountain = new Sprite(mountainTex)
    mountain.x = 0
    mountain.y = GROUND_Y - 64
    bg.addChild(mountain)
  }

  // Ground (tiled)
  const groundYellowTex = textures['objects/ground_yellow.png']
  const groundRedTex = textures['objects/ground_red.png']
  const groundLineTex = textures['objects/ground_line.png']
  const groundLeftTex = textures['objects/ground_line_leftmost.png']
  const groundRightTex = textures['objects/ground_line_rightmost.png']

  // Ground line row
  for (let i = 0; i < COURT_WIDTH / 16; i++) {
    let tex = groundLineTex
    if (i === 0) tex = groundLeftTex
    if (i === COURT_WIDTH / 16 - 1) tex = groundRightTex
    const tile = new Sprite(tex)
    tile.x = i * 16
    tile.y = GROUND_Y
    bg.addChild(tile)
  }

  // Ground fill rows
  for (let y = GROUND_Y + 16; y < COURT_HEIGHT; y += 16) {
    for (let x = 0; x < COURT_WIDTH; x += 16) {
      const tex = (x / 16 + y / 16) % 2 === 0 ? groundYellowTex : groundRedTex
      const tile = new Sprite(tex)
      tile.x = x
      tile.y = y
      bg.addChild(tile)
    }
  }

  // Net pillar
  const netPillarTex = textures['objects/net_pillar.png']
  const netTopTex = textures['objects/net_pillar_top.png']
  if (netPillarTex && netTopTex) {
    for (let y = NET_TOP_Y; y < GROUND_Y; y += 8) {
      const pillar = new Sprite(netPillarTex)
      pillar.x = NET_X - 4
      pillar.y = y
      bg.addChild(pillar)
    }
    const top = new Sprite(netTopTex)
    top.x = NET_X - 4
    top.y = NET_TOP_Y - 8
    bg.addChild(top)
  }

  stage.addChild(bg)

  // Shadows
  const shadowTex = textures['objects/shadow.png']
  const shadowP1 = new Sprite(shadowTex)
  shadowP1.anchor.set(0.5)
  shadowP1.y = SHADOW_Y
  const shadowP2 = new Sprite(shadowTex)
  shadowP2.anchor.set(0.5)
  shadowP2.y = SHADOW_Y
  const shadowBall = new Sprite(shadowTex)
  shadowBall.anchor.set(0.5)
  shadowBall.y = SHADOW_Y
  stage.addChild(shadowP1, shadowP2, shadowBall)

  // Players
  const playerTextures = buildPlayerTextures(textures)
  const player1 = new AnimatedSprite(playerTextures)
  player1.anchor.set(0.5)
  const player2 = new AnimatedSprite(playerTextures)
  player2.anchor.set(0.5)
  player2.scale.x = -1 // player 2 faces left
  stage.addChild(player1, player2)

  // Ball
  const ballTextures = buildBallTextures(textures)
  const ball = new AnimatedSprite(ballTextures)
  ball.anchor.set(0.5)
  stage.addChild(ball)

  return { bg, player1, player2, ball, shadowP1, shadowP2, shadowBall }
}

export function GameCanvas({ gameState, width = COURT_WIDTH, height = COURT_HEIGHT }: GameCanvasProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const appRef = useRef<Application | null>(null)
  const graphicsRef = useRef<Graphics | null>(null)
  const spritesRef = useRef<SpriteObjects | null>(null)
  const prevStateRef = useRef<GameState | null>(null)
  const currentStateRef = useRef<GameState | null>(null)
  const lerpFactorRef = useRef(0)
  const animFrameRef = useRef(0)
  const frameCounterRef = useRef(0)

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
      appRef.current = app

      // Try loading spritesheet
      try {
        const sheet = await Assets.load<Spritesheet>(SPRITE_SHEET_PATH)
        if (destroyed) return

        const textures = sheet.textures
        if (textures && Object.keys(textures).length > 0) {
          spritesRef.current = buildSpriteScene(textures, app.stage)
          return
        }
      } catch {
        // Sprite loading failed — fall back to Graphics primitives
      }

      // Fallback: Graphics-based rendering
      const gfx = new Graphics()
      app.stage.addChild(gfx)
      graphicsRef.current = gfx
    }

    init()

    return () => {
      destroyed = true
      if (appRef.current) {
        appRef.current.destroy(true)
        appRef.current = null
      }
      graphicsRef.current = null
      spritesRef.current = null
    }
  }, [width, height])

  useEffect(() => {
    if (gameState) {
      prevStateRef.current = currentStateRef.current ?? gameState
      currentStateRef.current = gameState
      lerpFactorRef.current = 0
      frameCounterRef.current++
    }
  }, [gameState])

  const drawSprites = useCallback((state: GameState) => {
    const sprites = spritesRef.current
    if (!sprites) return

    const fc = frameCounterRef.current

    // Player 1
    sprites.player1.x = state.player1.x
    sprites.player1.y = state.player1.y
    sprites.player1.scale.x = 1
    const p1Frame = inferPlayerFrame(state.player1.vx, state.player1.vy, fc)
    sprites.player1.gotoAndStop(Math.min(p1Frame, sprites.player1.totalFrames - 1))
    sprites.shadowP1.x = state.player1.x

    // Player 2
    sprites.player2.x = state.player2.x
    sprites.player2.y = state.player2.y
    sprites.player2.scale.x = -1
    const p2Frame = inferPlayerFrame(state.player2.vx, state.player2.vy, fc)
    sprites.player2.gotoAndStop(Math.min(p2Frame, sprites.player2.totalFrames - 1))
    sprites.shadowP2.x = state.player2.x

    // Ball
    sprites.ball.x = state.ball.x
    sprites.ball.y = state.ball.y
    const ballFrame = Math.abs(Math.floor(state.ball.rotation ?? 0)) % 5
    sprites.ball.gotoAndStop(Math.min(ballFrame, sprites.ball.totalFrames - 1))
    sprites.shadowBall.x = state.ball.x
  }, [])

  const drawGraphics = useCallback((state: GameState) => {
    const gfx = graphicsRef.current
    if (!gfx) return

    gfx.clear()

    // Sky
    gfx.rect(0, 0, COURT_WIDTH, GROUND_Y)
    gfx.fill(0x87ceeb)

    // Ground
    gfx.rect(0, GROUND_Y, COURT_WIDTH, COURT_HEIGHT - GROUND_Y)
    gfx.fill(0x4a7c59)

    // Net pillar
    gfx.rect(NET_X - NET_HALF_WIDTH / 2, NET_TOP_Y, NET_HALF_WIDTH / 2, GROUND_Y - NET_TOP_Y)
    gfx.fill(0xcccccc)

    // Net top
    gfx.rect(NET_X - NET_HALF_WIDTH, NET_TOP_Y - 4, NET_HALF_WIDTH * 2, 4)
    gfx.fill(0xffffff)

    // Player 1
    gfx.circle(state.player1.x, state.player1.y, PLAYER_HALF)
    gfx.fill(0xffd700)
    gfx.circle(state.player1.x, state.player1.y, PLAYER_HALF)
    gfx.stroke({ width: 2, color: 0xb8960f })
    gfx.circle(state.player1.x + 8, state.player1.y - 8, 4)
    gfx.fill(0x000000)

    // Player 2
    gfx.circle(state.player2.x, state.player2.y, PLAYER_HALF)
    gfx.fill(0xff4444)
    gfx.circle(state.player2.x, state.player2.y, PLAYER_HALF)
    gfx.stroke({ width: 2, color: 0xaa2222 })
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
        lerpFactorRef.current = Math.min(lerpFactorRef.current + 1 / 2, 1)
        const interpolated = lerpState(prev, next, lerpFactorRef.current)
        if (spritesRef.current) {
          drawSprites(interpolated)
        } else {
          drawGraphics(interpolated)
        }
      } else if (next) {
        if (spritesRef.current) {
          drawSprites(next)
        } else {
          drawGraphics(next)
        }
      }

      animFrameRef.current = requestAnimationFrame(tick)
    }

    animFrameRef.current = requestAnimationFrame(tick)

    return () => {
      running = false
      cancelAnimationFrame(animFrameRef.current)
    }
  }, [drawSprites, drawGraphics])

  return <div ref={containerRef} className="game-canvas" />
}
