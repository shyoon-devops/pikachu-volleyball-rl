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
  TextureSource,
} from 'pixi.js'
import type { GameState } from '../../lib/types'
import './GameCanvas.css'

// Pixel-art rendering: force NEAREST filter globally so texture atlas tiles do
// not bleed their edge texels into neighboring transparent gutter pixels under
// DPR>1 sub-pixel sampling. Without this PixiJS v8 defaults to LINEAR, which
// produced visible RGB vertical stripes along the tiled sky background.
// Must be set before Assets.load() so sprite_sheet.png inherits the mode.
TextureSource.defaultOptions.scaleMode = 'nearest'

// ── Original game constants (from physics.js) ──
const COURT_WIDTH = 432
const COURT_HEIGHT = 304
const NET_X = 216
const NET_TOP_Y = 176
const NET_HALF_WIDTH = 25
const PLAYER_HALF = 32
const BALL_RADIUS = 20
const PLAYER_GROUND_Y = 244
const SHADOW_Y = 273
const NUM_CLOUDS = 10

// Power-hit detection threshold (heuristic — backend doesn't send isPowerHit)
const POWER_HIT_SPEED = 25

const SPRITE_SHEET_PATH = '/assets/sprite_sheet.json'

interface GameCanvasProps {
  gameState: GameState | null
  /**
   * Optional — forces a fixed CSS pixel size. When omitted the canvas fills
   * its container (CSS handles responsive scaling via aspect-ratio).
   */
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

// ── Player animation frame mapping (matches original getFrameNumberForPlayerAnimatedSprite) ──
// States: 0=idle(5fr), 1=jump(5fr), 2=power_hit(5fr), 3=dive(2fr), 4=lying(1fr), 5=win(5fr), 6=lose(5fr)
// Total: 28 frames
// NOTE: getPlayerFrameFromState is the accurate mapping used by the original game.
// It requires (state, frameNumber) from the backend. Currently unused because our backend
// only sends velocity data, so we use inferPlayerFrame below as a heuristic.
// When backend adds state/frameNumber fields, switch to this function.
// function getPlayerFrameFromState(state: number, frameNumber: number): number {
//   if (state < 4) return 5 * state + frameNumber
//   if (state === 4) return 17 + frameNumber
//   return 18 + 5 * (state - 5) + frameNumber
// }

/** Infer pikachu animation frame index from velocity (backend doesn't send state/frameNumber). */
function inferPlayerFrame(vx: number, vy: number, frameCounter: number): number {
  if (vy !== 0) {
    // Jump: state=1, 5 frames (indices 5-9)
    return 5 + (frameCounter % 5)
  }
  if (Math.abs(vx) > 0) {
    // Walk-like motion: use state=0 arm swing
    return frameCounter % 5
  }
  // Idle: state=0
  return frameCounter % 5
}

/** Build the ordered texture array for pikachu AnimatedSprite (28 frames total). */
function buildPlayerTextures(textures: Record<string, Texture>): Texture[] {
  const result: Texture[] = []
  for (let i = 0; i < 7; i++) {
    if (i === 3) {
      result.push(textures['pikachu/pikachu_3_0.png'])
      result.push(textures['pikachu/pikachu_3_1.png'])
    } else if (i === 4) {
      result.push(textures['pikachu/pikachu_4_0.png'])
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

function buildNumberTextures(textures: Record<string, Texture>): Texture[] {
  const result: Texture[] = []
  for (let i = 0; i < 10; i++) {
    result.push(textures[`number/number_${i}.png`])
  }
  return result
}

// ── Cloud model (ported from cloud_and_wave.js) ──
interface CloudModel {
  x: number
  y: number
  xVelocity: number
  sizeTurn: number
}

function createCloud(): CloudModel {
  return {
    x: -68 + Math.floor(Math.random() * (COURT_WIDTH + 68)),
    y: Math.floor(Math.random() * 152),
    xVelocity: 1 + Math.floor(Math.random() * 2),
    sizeTurn: Math.floor(Math.random() * 11),
  }
}

function cloudSizeDiff(c: CloudModel): number {
  return 5 - Math.abs(c.sizeTurn - 5)
}

function tickClouds(clouds: CloudModel[]): void {
  for (const c of clouds) {
    c.x += c.xVelocity
    if (c.x > COURT_WIDTH) {
      c.x = -68
      c.y = Math.floor(Math.random() * 152)
      c.xVelocity = 1 + Math.floor(Math.random() * 2)
    }
    c.sizeTurn = (c.sizeTurn + 1) % 11
  }
}

// ── Wave model ──
interface WaveModel {
  verticalCoord: number
  velocity: number
  yCoords: number[]
}

function createWave(): WaveModel {
  const yCoords: number[] = []
  for (let i = 0; i < COURT_WIDTH / 16; i++) {
    yCoords.push(314)
  }
  return { verticalCoord: 0, velocity: 2, yCoords }
}

function tickWave(w: WaveModel): void {
  w.verticalCoord += w.velocity
  if (w.verticalCoord > 32) {
    w.verticalCoord = 32
    w.velocity = -1
  } else if (w.verticalCoord < 0 && w.velocity < 0) {
    w.velocity = 2
    w.verticalCoord = -Math.floor(Math.random() * 40)
  }
  for (let i = 0; i < COURT_WIDTH / 16; i++) {
    w.yCoords[i] = 314 - w.verticalCoord + Math.floor(Math.random() * 3)
  }
}

// ── Scene objects ──
interface SpriteObjects {
  bg: Container
  cloudContainer: Container
  waveContainer: Container
  player1: AnimatedSprite
  player2: AnimatedSprite
  ball: AnimatedSprite
  ballHyper: Sprite
  ballTrail: Sprite
  shadowP1: Sprite
  shadowP2: Sprite
  shadowBall: Sprite
  scoreBoard1: Container
  scoreBoard2: Container
}

function buildScoreBoard(
  numberTextures: Texture[],
): Container {
  const board = new Container()
  // units digit (right)
  const units = new AnimatedSprite(numberTextures)
  units.anchor.set(0, 0)
  units.x = 32
  units.y = 0
  board.addChild(units)
  // tens digit (left)
  const tens = new AnimatedSprite(numberTextures)
  tens.anchor.set(0, 0)
  tens.x = 0
  tens.y = 0
  tens.visible = false
  board.addChild(tens)
  return board
}

function buildSpriteScene(
  textures: Record<string, Texture>,
  stage: Container,
): SpriteObjects {
  const bg = new Container()

  // ── Sky (12 rows of 16px, y=0..191) — matches original ──
  const skyTex = textures['objects/sky_blue.png']
  for (let j = 0; j < 12; j++) {
    for (let i = 0; i < COURT_WIDTH / 16; i++) {
      const tile = new Sprite(skyTex)
      tile.x = i * 16
      tile.y = j * 16
      bg.addChild(tile)
    }
  }

  // ── Mountain at y=188 ──
  const mountainTex = textures['objects/mountain.png']
  if (mountainTex) {
    const mountain = new Sprite(mountainTex)
    mountain.x = 0
    mountain.y = 188
    bg.addChild(mountain)
  }

  // ── Ground red row at y=248 ──
  const groundRedTex = textures['objects/ground_red.png']
  for (let i = 0; i < COURT_WIDTH / 16; i++) {
    const tile = new Sprite(groundRedTex)
    tile.x = i * 16
    tile.y = 248
    bg.addChild(tile)
  }

  // ── Ground line row at y=264 ──
  const groundLineTex = textures['objects/ground_line.png']
  const groundLeftTex = textures['objects/ground_line_leftmost.png']
  const groundRightTex = textures['objects/ground_line_rightmost.png']
  for (let i = 0; i < COURT_WIDTH / 16; i++) {
    let tex = groundLineTex
    if (i === 0) tex = groundLeftTex
    if (i === COURT_WIDTH / 16 - 1) tex = groundRightTex
    const tile = new Sprite(tex)
    tile.x = i * 16
    tile.y = 264
    bg.addChild(tile)
  }

  // ── Ground yellow rows at y=280, y=296 ──
  const groundYellowTex = textures['objects/ground_yellow.png']
  for (let j = 0; j < 2; j++) {
    for (let i = 0; i < COURT_WIDTH / 16; i++) {
      const tile = new Sprite(groundYellowTex)
      tile.x = i * 16
      tile.y = 280 + j * 16
      bg.addChild(tile)
    }
  }

  // ── Net pillar ──
  const netPillarTex = textures['objects/net_pillar.png']
  const netTopTex = textures['objects/net_pillar_top.png']
  if (netPillarTex && netTopTex) {
    const top = new Sprite(netTopTex)
    top.x = 213
    top.y = NET_TOP_Y
    bg.addChild(top)
    for (let j = 0; j < 12; j++) {
      const pillar = new Sprite(netPillarTex)
      pillar.x = 213
      pillar.y = 184 + j * 8
      bg.addChild(pillar)
    }
  }

  stage.addChild(bg)

  // ── Clouds ──
  const cloudContainer = new Container()
  const cloudTex = textures['objects/cloud.png']
  if (cloudTex) {
    for (let i = 0; i < NUM_CLOUDS; i++) {
      const cloud = new Sprite(cloudTex)
      cloud.anchor.set(0, 0)
      cloudContainer.addChild(cloud)
    }
  }
  stage.addChild(cloudContainer)

  // ── Waves ──
  const waveContainer = new Container()
  const waveTex = textures['objects/wave.png']
  if (waveTex) {
    for (let i = 0; i < COURT_WIDTH / 16; i++) {
      const tile = new Sprite(waveTex)
      tile.x = i * 16
      tile.y = 0
      waveContainer.addChild(tile)
    }
  }
  stage.addChild(waveContainer)

  // ── Shadows ──
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

  // ── Players ──
  const playerTextures = buildPlayerTextures(textures)
  const player1 = new AnimatedSprite(playerTextures)
  player1.anchor.set(0.5)
  const player2 = new AnimatedSprite(playerTextures)
  player2.anchor.set(0.5)
  player2.scale.x = -1
  stage.addChild(player1, player2)

  // ── Ball effects ──
  const ballTrailTex = textures['ball/ball_trail.png']
  const ballHyperTex = textures['ball/ball_hyper.png']
  const ballTrail = new Sprite(ballTrailTex)
  ballTrail.anchor.set(0.5)
  ballTrail.visible = false
  const ballHyper = new Sprite(ballHyperTex)
  ballHyper.anchor.set(0.5)
  ballHyper.visible = false
  stage.addChild(ballTrail, ballHyper)

  // ── Ball ──
  const ballTextures = buildBallTextures(textures)
  const ball = new AnimatedSprite(ballTextures)
  ball.anchor.set(0.5)
  stage.addChild(ball)

  // ── Score boards ──
  const numberTextures = buildNumberTextures(textures)
  const scoreBoard1 = buildScoreBoard(numberTextures)
  scoreBoard1.x = 14
  scoreBoard1.y = 10
  const scoreBoard2 = buildScoreBoard(numberTextures)
  scoreBoard2.x = COURT_WIDTH - 32 - 32 - 14
  scoreBoard2.y = 10
  stage.addChild(scoreBoard1, scoreBoard2)

  return {
    bg,
    cloudContainer,
    waveContainer,
    player1,
    player2,
    ball,
    ballHyper,
    ballTrail,
    shadowP1,
    shadowP2,
    shadowBall,
    scoreBoard1,
    scoreBoard2,
  }
}

export function GameCanvas({ gameState, width, height }: GameCanvasProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const appRef = useRef<Application | null>(null)
  const graphicsRef = useRef<Graphics | null>(null)
  const spritesRef = useRef<SpriteObjects | null>(null)
  const prevStateRef = useRef<GameState | null>(null)
  const currentStateRef = useRef<GameState | null>(null)
  const prevBallRef = useRef<{ x: number; y: number } | null>(null)
  const lerpFactorRef = useRef(0)
  const animFrameRef = useRef(0)
  const frameCounterRef = useRef(0)
  const cloudsRef = useRef<CloudModel[]>([])
  const waveRef = useRef<WaveModel>(createWave())

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
        // Pixel-art game — smoothing produces sub-pixel texel bleed which
        // manifested as RGB vertical stripes on the tiled sky.
        antialias: false,
        resolution: window.devicePixelRatio || 1,
        autoDensity: true,
        // Snap sprite positions to integer pixels to further prevent
        // sub-pixel sampling of atlas edge texels.
        roundPixels: true,
      })

      if (destroyed) {
        app.destroy(true)
        return
      }

      const canvas = app.canvas as HTMLCanvasElement
      // When width/height props are provided, force a fixed pixel size.
      // Otherwise let CSS (width:100%; height:100% on .game-canvas canvas) scale
      // the canvas responsively while preserving the 432:304 aspect ratio.
      if (width !== undefined) canvas.style.width = `${width}px`
      if (height !== undefined) canvas.style.height = `${height}px`
      container.appendChild(canvas)
      appRef.current = app

      // Try loading spritesheet
      try {
        const sheet = await Assets.load<Spritesheet>(SPRITE_SHEET_PATH)
        if (destroyed) return

        const textures = sheet.textures
        if (textures && Object.keys(textures).length > 0) {
          spritesRef.current = buildSpriteScene(textures, app.stage)
          // Initialize clouds
          const clouds: CloudModel[] = []
          for (let i = 0; i < NUM_CLOUDS; i++) {
            clouds.push(createCloud())
          }
          cloudsRef.current = clouds
          waveRef.current = createWave()
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

    // ── Clouds & Waves (ambient, independent of game state) ──
    const clouds = cloudsRef.current
    if (clouds.length > 0) {
      tickClouds(clouds)
      for (let i = 0; i < clouds.length && i < sprites.cloudContainer.children.length; i++) {
        const c = clouds[i]
        const sd = cloudSizeDiff(c)
        const sprite = sprites.cloudContainer.children[i]
        sprite.x = c.x - sd
        sprite.y = c.y - sd
        sprite.width = 48 + 2 * sd
        sprite.height = 24 + 2 * sd
      }
    }

    const wave = waveRef.current
    tickWave(wave)
    for (let i = 0; i < sprites.waveContainer.children.length; i++) {
      sprites.waveContainer.children[i].y = wave.yCoords[i] ?? 314
    }

    // ── Player 1 ──
    sprites.player1.x = state.player1.x
    sprites.player1.y = state.player1.y
    sprites.player1.scale.x = 1
    const p1Frame = inferPlayerFrame(state.player1.vx, state.player1.vy, fc)
    sprites.player1.gotoAndStop(Math.min(p1Frame, sprites.player1.totalFrames - 1))
    sprites.shadowP1.x = state.player1.x

    // ── Player 2 ──
    sprites.player2.x = state.player2.x
    sprites.player2.y = state.player2.y
    sprites.player2.scale.x = -1
    const p2Frame = inferPlayerFrame(state.player2.vx, state.player2.vy, fc)
    sprites.player2.gotoAndStop(Math.min(p2Frame, sprites.player2.totalFrames - 1))
    sprites.shadowP2.x = state.player2.x

    // ── Ball ──
    sprites.ball.x = state.ball.x
    sprites.ball.y = state.ball.y
    const ballFrame = Math.abs(Math.floor(state.ball.rotation ?? 0)) % 5
    sprites.ball.gotoAndStop(Math.min(ballFrame, sprites.ball.totalFrames - 1))
    sprites.shadowBall.x = state.ball.x

    // ── Ball power-hit effects (heuristic: high speed = power hit) ──
    const ballSpeed = Math.sqrt(state.ball.vx * state.ball.vx + state.ball.vy * state.ball.vy)
    const isPowerHit = ballSpeed > POWER_HIT_SPEED
    const prev = prevBallRef.current

    if (isPowerHit && prev) {
      sprites.ballHyper.x = prev.x
      sprites.ballHyper.y = prev.y
      sprites.ballHyper.visible = true
      sprites.ballTrail.x = (prev.x + state.ball.x) / 2
      sprites.ballTrail.y = (prev.y + state.ball.y) / 2
      sprites.ballTrail.visible = true
    } else {
      sprites.ballHyper.visible = false
      sprites.ballTrail.visible = false
    }
    prevBallRef.current = { x: state.ball.x, y: state.ball.y }

    // ── Score boards ──
    updateScoreBoard(sprites.scoreBoard1, state.score1)
    updateScoreBoard(sprites.scoreBoard2, state.score2)
  }, [])

  const drawGraphics = useCallback((state: GameState) => {
    const gfx = graphicsRef.current
    if (!gfx) return

    gfx.clear()

    // Sky
    gfx.rect(0, 0, COURT_WIDTH, PLAYER_GROUND_Y)
    gfx.fill(0x87ceeb)

    // Ground
    gfx.rect(0, PLAYER_GROUND_Y, COURT_WIDTH, COURT_HEIGHT - PLAYER_GROUND_Y)
    gfx.fill(0x4a7c59)

    // Net pillar
    gfx.rect(NET_X - NET_HALF_WIDTH / 2, NET_TOP_Y, NET_HALF_WIDTH / 2, PLAYER_GROUND_Y - NET_TOP_Y)
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

    // Score text (fallback)
    // Graphics API doesn't support text easily; scores shown in GameOverlay
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

// ── Helpers ──

function updateScoreBoard(board: Container, score: number): void {
  const units = board.children[0] as AnimatedSprite
  const tens = board.children[1] as AnimatedSprite
  if (!units || !tens) return

  units.gotoAndStop(score % 10)
  if (score >= 10) {
    tens.visible = true
    tens.gotoAndStop(Math.floor(score / 10) % 10)
  } else {
    tens.visible = false
  }
}
