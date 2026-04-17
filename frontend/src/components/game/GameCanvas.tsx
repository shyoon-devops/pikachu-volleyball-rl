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
import {
  computePowerHitTrail,
  type BallHistoryPoint,
} from './powerHitTrail'
import { computePunchEffect } from './punchEffect'
import { computeGameEndOverlay } from './gameEndOverlay'
import { inferPlayerFrame } from './playerFrame'
import {
  Cloud,
  Wave,
  cloudAndWaveEngine,
  NUM_OF_CLOUDS,
} from './cloudAndWave'
import { resolveAudioTriggers } from './audioTriggers'
import { getPikaAudio } from '../../lib/pikaAudio'
import './GameCanvas.css'

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
// Net pillar x-anchor in the original engine (view.js:785, 789).
// Distinct from NET_X (216) which is the collision-axis centre — the
// sprite sits 3px to the left of that centre line.
const NET_PILLAR_X = 213
// Ball sprite textures: 6 frames total, ball_0..4 plus ball_hyper at
// index 5. The engine's `fine_rotation` maxes at 50, which integer-
// divides to rotation=5 — deliberately rendering the hyper-ball frame
// (the "hyper ball glitch" described in physics.js:410-414). We clamp
// to [0,5] but never modulo away index 5.
const BALL_TEXTURE_COUNT = 6

// How many server ball positions to keep for the power-hit trail.
// Original engine renders ballHyper at ball.previousX/Y (t-1) and
// ballTrail at ball.previousPreviousX/Y (t-2) — so we need a 3-slot
// ring buffer [t-2, t-1, t] when BE doesn't include those fields.
const BALL_HISTORY_LEN = 3

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
      // Engine-authoritative animation fields must survive interpolation
      // unchanged — they are discrete indices, not positions. Taking
      // `next` pins the sprite to the latest server tick.
      state: next.player1.state,
      frameNumber: next.player1.frameNumber,
      divingDirection: next.player1.divingDirection,
      isWinner: next.player1.isWinner,
      gameEnded: next.player1.gameEnded,
    },
    player2: {
      x: lerp(prev.player2.x, next.player2.x, t),
      y: lerp(prev.player2.y, next.player2.y, t),
      vx: next.player2.vx,
      vy: next.player2.vy,
      isJumping: next.player2.isJumping ?? false,
      isDiving: next.player2.isDiving ?? false,
      isPowerHitting: next.player2.isPowerHitting ?? false,
      state: next.player2.state,
      frameNumber: next.player2.frameNumber,
      divingDirection: next.player2.divingDirection,
      isWinner: next.player2.isWinner,
      gameEnded: next.player2.gameEnded,
    },
    ball: {
      x: lerp(prev.ball.x, next.ball.x, t),
      y: lerp(prev.ball.y, next.ball.y, t),
      vx: next.ball.vx,
      vy: next.ball.vy,
      rotation: lerp(prev.ball.rotation ?? 0, next.ball.rotation ?? 0, t),
      // Power-hit flag + historical positions are NOT interpolated —
      // they are per-frame authoritative signals from the engine.
      // Taking `next` value preserves the original game's visual
      // semantics (hyper/trail sprites render at discrete historical
      // positions, not smoothed ones).
      isPowerHit: next.ball.isPowerHit,
      previousX: next.ball.previousX,
      previousY: next.ball.previousY,
      previousPreviousX: next.ball.previousPreviousX,
      previousPreviousY: next.ball.previousPreviousY,
      // Punch-effect markers are per-frame authoritative (radius decays
      // engine-side by 2/frame, view.js:502-511). Don't interpolate — the
      // ring needs to anchor to the impact point and shrink on the
      // engine's tick schedule.
      punchEffectX: next.ball.punchEffectX,
      punchEffectY: next.ball.punchEffectY,
      punchEffectRadius: next.ball.punchEffectRadius,
    },
    score1: next.score1,
    score2: next.score2,
    frame: next.frame,
    isRoundOver: next.isRoundOver,
    isGameEnded: next.isGameEnded,
    gameEndFrameCounter: next.gameEndFrameCounter,
    // Display state-machine fields are per-tick discrete signals from
    // the engine — never interpolate. The fade alpha animation is
    // already engine-driven (1/16 per frame), so taking `next` shows
    // exactly the engine-authoritative value each render.
    stateName: next.stateName,
    slowMotionFramesLeft: next.slowMotionFramesLeft,
    fadeBlackAlpha: next.fadeBlackAlpha,
    readyMessageVisible: next.readyMessageVisible,
  }
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
  // Index 5 is `ball_hyper.png` — rendered when `fine_rotation === 50`
  // (the original "hyper ball" edge case, physics.js:410-414). Keep all
  // 6 textures so the engine's rotation=5 path lights up faithfully
  // instead of silently remapping to ball_0.
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

// Cloud/Wave models + engine live in ./cloudAndWave (1:1 port of the
// original cloud_and_wave.js). GameCanvas just holds the instances and
// forwards their state onto Pixi sprites each frame.

// ── Scene objects ──
interface SpriteObjects {
  bg: Container
  cloudContainer: Container
  waveContainer: Container
  player1: AnimatedSprite
  player2: AnimatedSprite
  // Per-player motion-blur trail — a second AnimatedSprite mirroring the
  // current pose offset behind the player along its velocity vector.
  // Rendered below the player sprite, made visible only while diving.
  afterimageP1: AnimatedSprite
  afterimageP2: AnimatedSprite
  ball: AnimatedSprite
  ballHyper: Sprite
  ballTrail: Sprite
  // Radial white "punch" ring drawn on the impact frame of a successful
  // hit — anchored at the impact point, shrinking 2px/frame. Ported
  // from view.js:502-511.
  punch: Sprite
  shadowP1: Sprite
  shadowP2: Sprite
  shadowBall: Sprite
  scoreBoard1: Container
  scoreBoard2: Container
  // "GAME END" overlay rendered during the 211-frame gameEnd window
  // (view.js:377, 622-645). Sprite anchor stays at (0, 0) so the
  // computeGameEndOverlay math — which derives a top-left position
  // from the centre plus increments — lines up with view.js directly.
  gameEndMessage: Sprite
  // Full-screen black fade overlay (view.js::FadeInOut). Alpha is
  // driven by `state.fadeBlackAlpha` every frame; visibility is gated
  // by `alpha > 0` so the overlay doesn't intercept events when idle.
  fadeOverlay: Sprite
  // "READY" sprite blinked during `beforeStartOfNextRound`. Toggled
  // visible/hidden from `state.readyMessageVisible` (the BE engine
  // already drives the 5-frame on/off cadence — pikavolley.js:443-444).
  readyMessage: Sprite
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

  // ── Net pillar (1:1 from view.js:783-790) ──
  //   top sprite at (NET_PILLAR_X, NET_TOP_Y) = (213, 176)
  //   12 tiling pillar segments stepping 8px from y=184
  const netPillarTex = textures['objects/net_pillar.png']
  const netTopTex = textures['objects/net_pillar_top.png']
  if (netPillarTex && netTopTex) {
    const top = new Sprite(netTopTex)
    top.x = NET_PILLAR_X
    top.y = NET_TOP_Y
    bg.addChild(top)
    for (let j = 0; j < 12; j++) {
      const pillar = new Sprite(netPillarTex)
      pillar.x = NET_PILLAR_X
      pillar.y = 184 + j * 8
      bg.addChild(pillar)
    }
  }

  stage.addChild(bg)

  // ── Clouds (view.js:904-915 makeCloudContainer) ──
  const cloudContainer = new Container()
  const cloudTex = textures['objects/cloud.png']
  if (cloudTex) {
    for (let i = 0; i < NUM_OF_CLOUDS; i++) {
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
  // Motion-blur afterimages are added *first* so they render beneath
  // the player sprite (Pixi draws children in insertion order). Both
  // start hidden — updateDiveAfterimage flips visibility per frame.
  const afterimageP1 = new AnimatedSprite(playerTextures)
  afterimageP1.anchor.set(0.5)
  afterimageP1.visible = false
  const afterimageP2 = new AnimatedSprite(playerTextures)
  afterimageP2.anchor.set(0.5)
  afterimageP2.visible = false
  stage.addChild(afterimageP1, afterimageP2)

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

  // ── Punch ring (above ball, view.js:398) ──
  // Added AFTER ball so the ring sits in front of it — matches
  // `container.addChild(this.punch)` ordering after the ball in the
  // original. Starts hidden; `drawSprites` toggles on punchEffectRadius.
  const punchTex = textures['ball/ball_punch.png']
  const punch = new Sprite(punchTex)
  punch.anchor.set(0.5)
  punch.visible = false
  stage.addChild(punch)

  // ── Score boards (view.js:363-366, 415-418) ──
  // Each board has a tens + units AnimatedSprite pinned to the number
  // atlas (number_0..9.png). `scoreBoard2.x` = 432 - 32 - 32 - 14 keeps
  // the two-digit area 14px from the right-hand edge, matching the
  // original UI chrome.
  const numberTextures = buildNumberTextures(textures)
  const scoreBoard1 = buildScoreBoard(numberTextures)
  scoreBoard1.x = 14
  scoreBoard1.y = 10
  const scoreBoard2 = buildScoreBoard(numberTextures)
  scoreBoard2.x = COURT_WIDTH - 32 - 32 - 14
  scoreBoard2.y = 10
  stage.addChild(scoreBoard1, scoreBoard2)

  // ── "GAME END" overlay (view.js:377, 622-645) ──
  // Added last so it sits on top of everything else. Hidden by default;
  // drawSprites gates visibility on isGameEnded + gameEndFrameCounter.
  const gameEndTex = textures['messages/common/game_end.png']
  const gameEndMessage = new Sprite(gameEndTex)
  gameEndMessage.anchor.set(0, 0)
  gameEndMessage.visible = false
  stage.addChild(gameEndMessage)

  // ── READY blink (view.js:376, 605-615) ──
  // Anchor at (0, 0), positioned at (176, 38) per view.js:413-414.
  // Hidden by default; readyMessageVisible toggles each render frame.
  const readyTex = textures['messages/common/ready.png']
  const readyMessage = new Sprite(readyTex)
  readyMessage.anchor.set(0, 0)
  readyMessage.x = 176
  readyMessage.y = 38
  readyMessage.visible = false
  stage.addChild(readyMessage)

  // ── Black fade overlay (view.js::FadeInOut, 651-700) ──
  // Stretched to cover the whole 432×304 court. Added last so it sits
  // ABOVE every other sprite — including the gameEnd message and the
  // READY blink. The original FadeInOut keeps the ready message
  // visible THROUGH the fade-in (so it pulses behind a fading curtain),
  // which works because PixiJS renders children-of-stage in insertion
  // order; placing fadeOverlay after readyMessage matches that.
  const blackTex = textures['objects/black.png']
  const fadeOverlay = new Sprite(blackTex)
  fadeOverlay.anchor.set(0, 0)
  fadeOverlay.width = COURT_WIDTH
  fadeOverlay.height = COURT_HEIGHT
  fadeOverlay.x = 0
  fadeOverlay.y = 0
  fadeOverlay.alpha = 0
  fadeOverlay.visible = false
  stage.addChild(fadeOverlay)

  return {
    bg,
    cloudContainer,
    waveContainer,
    player1,
    player2,
    afterimageP1,
    afterimageP2,
    ball,
    ballHyper,
    ballTrail,
    punch,
    shadowP1,
    shadowP2,
    shadowBall,
    scoreBoard1,
    scoreBoard2,
    gameEndMessage,
    fadeOverlay,
    readyMessage,
  }
}

export function GameCanvas({ gameState, width, height }: GameCanvasProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const appRef = useRef<Application | null>(null)
  const graphicsRef = useRef<Graphics | null>(null)
  const spritesRef = useRef<SpriteObjects | null>(null)
  const prevStateRef = useRef<GameState | null>(null)
  const currentStateRef = useRef<GameState | null>(null)
  // Ring buffer of the last 3 server ball positions [t-2, t-1, t].
  // Populated each time a new gameState arrives (authoritative 30fps
  // server tick) — NOT on the 60fps rAF loop, so the sprites always
  // render at discrete historical positions matching the original
  // engine's `previousX` / `previousPreviousX` semantics.
  const ballHistoryRef = useRef<BallHistoryPoint[]>([])
  const lerpFactorRef = useRef(0)
  const animFrameRef = useRef(0)
  const frameCounterRef = useRef(0)
  const cloudsRef = useRef<Cloud[]>([])
  const waveRef = useRef<Wave>(new Wave())

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
        // Pixel-art sprites (16×16 sky tiles, 64×64 pikachu, 40×40 ball):
        //   antialias:false  — canvas edge antialias adds no value to
        //     integer-grid pixel art and can introduce 1px fringing at
        //     the stage border.
        //   roundPixels:true — RL physics sends fractional player/ball
        //     positions (e.g. x=123.7); without rounding the GPU samples
        //     at sub-pixel offsets and bleeds adjacent texels. Belt-and-
        //     suspenders with `scaleMode: 'nearest'` below.
        antialias: false,
        roundPixels: true,
        resolution: window.devicePixelRatio || 1,
        autoDensity: true,
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
          // Force nearest-neighbor sampling for all frames. Pixi v8
          // defaults to 'linear' (bilinear), which is the right call
          // for photographic textures but WRONG for pixel art — at
          // devicePixelRatio != 1 the GPU samples fractional texels and
          // the 2px transparent padding around each atlas frame bleeds
          // into the sprite edge. The 27-tile sky row made this read
          // as 27 vertical seams every 16px (designer report,
          // 2026-04-12).
          //
          // The spritesheet shares a single TextureSource across all
          // frames so one assignment covers the entire atlas.
          const sharedSource = Object.values(textures)[0]?.source
          if (sharedSource) {
            sharedSource.scaleMode = 'nearest'
          }
          spritesRef.current = buildSpriteScene(textures, app.stage)
          // Initialize 10 clouds + wave using the 1:1 port of
          // cloud_and_wave.js. Each Cloud seeds itself with randomized
          // x/y/velocity in its constructor; Wave starts at y=314
          // (bottom of the court) and oscillates 0→32 vertically.
          const clouds: Cloud[] = []
          for (let i = 0; i < NUM_OF_CLOUDS; i++) {
            clouds.push(new Cloud())
          }
          cloudsRef.current = clouds
          waveRef.current = new Wave()
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

      // ── SFX triggers (audio.js + pikavolley.js trigger points) ──
      // BE resets `sounds.*` at the start of each engine tick and sets
      // flags only on the triggering frame, so reading them straight
      // from the server gameState fires exactly once per tick. Firing
      // from this useEffect (rather than the 60fps rAF loop) is what
      // guarantees no double-play. Audio singleton is muted by default
      // — calls are cheap no-ops until the user unmutes.
      const triggers = resolveAudioTriggers(gameState)
      if (triggers.length > 0) {
        const audio = getPikaAudio()
        for (const t of triggers) audio.playSfx(t.name, t.pan)
      }
      // Maintain 3-slot ring buffer of server ball positions. Only the
      // last BALL_HISTORY_LEN entries are kept. The buffer feeds the
      // power-hit trail; see computePowerHitTrail() for how it's read.
      //
      // Reset on a round boundary (isRoundOver rising edge from BE's
      // 211-frame gameEnd window — pikavolley.js frameTotal.gameEnd) so
      // the first power hit of the next serve doesn't read stale
      // prev/prevPrev positions from the last rally's final frames.
      // Without this, the trail briefly renders from wherever the ball
      // landed back to the new serve point — a visible warp artifact.
      if (gameState.isRoundOver) {
        ballHistoryRef.current = [
          { x: gameState.ball.x, y: gameState.ball.y },
        ]
      } else {
        const hist = ballHistoryRef.current
        const pt: BallHistoryPoint = { x: gameState.ball.x, y: gameState.ball.y }
        ballHistoryRef.current =
          hist.length < BALL_HISTORY_LEN
            ? [...hist, pt]
            : [...hist.slice(hist.length - (BALL_HISTORY_LEN - 1)), pt]
      }
    }
  }, [gameState])

  const drawSprites = useCallback((state: GameState) => {
    const sprites = spritesRef.current
    if (!sprites) return

    const fc = frameCounterRef.current

    // ── Clouds & Waves (view.js:552-573 drawCloudsAndWave) ──
    // One engine tick advances both clouds and wave together, then we
    // flush each to its Pixi sprite. Sprite positions use the cloud's
    // size-compensated getters so width/height pulsing stays centered.
    const clouds = cloudsRef.current
    const wave = waveRef.current
    cloudAndWaveEngine(clouds, wave)
    for (
      let i = 0;
      i < clouds.length && i < sprites.cloudContainer.children.length;
      i++
    ) {
      const c = clouds[i]
      const sprite = sprites.cloudContainer.children[i]
      sprite.x = c.spriteTopLeftPointX
      sprite.y = c.spriteTopLeftPointY
      sprite.width = c.spriteWidth
      sprite.height = c.spriteHeight
    }
    for (let i = 0; i < sprites.waveContainer.children.length; i++) {
      sprites.waveContainer.children[i].y = wave.yCoords[i] ?? 314
    }

    // ── Player 1 (view.js:467-474) ──
    //   scale.x flips for diving/lying states per `divingDirection`;
    //   otherwise +1 (facing right, native sheet orientation).
    sprites.player1.x = state.player1.x
    sprites.player1.y = state.player1.y
    sprites.player1.scale.x = resolvePlayerScaleX(state.player1, 1)
    const p1Frame = inferPlayerFrame(state.player1, fc)
    sprites.player1.gotoAndStop(Math.min(p1Frame, sprites.player1.totalFrames - 1))
    sprites.shadowP1.x = state.player1.x
    // Dive afterimage: second sprite copy trailing behind player along
    // velocity vector, reduced alpha. Mirrors view.js's motion-blur look
    // for a slide without shipping a dedicated dust asset. Hidden when
    // not diving so idle/jump frames stay crisp.
    updateDiveAfterimage(sprites.afterimageP1, state.player1, p1Frame, 1)

    // ── Player 2 (view.js:476-483) ──
    //   P2 mirrors horizontally by default (scale.x = -1). Dive flips
    //   only when `divingDirection === 1` (dive toward own side).
    sprites.player2.x = state.player2.x
    sprites.player2.y = state.player2.y
    sprites.player2.scale.x = resolvePlayerScaleX(state.player2, -1)
    const p2Frame = inferPlayerFrame(state.player2, fc)
    sprites.player2.gotoAndStop(Math.min(p2Frame, sprites.player2.totalFrames - 1))
    sprites.shadowP2.x = state.player2.x
    updateDiveAfterimage(sprites.afterimageP2, state.player2, p2Frame, -1)

    // ── Ball (view.js:496-499) ──
    // Full 0-5 rotation index. Clamp instead of modulo so rotation=5
    // lights up ball_hyper (physics.js:410-414 "hyper ball glitch")
    // instead of being aliased back to ball_0.
    sprites.ball.x = state.ball.x
    sprites.ball.y = state.ball.y
    const rawRot = Math.floor(state.ball.rotation ?? 0)
    const ballFrame = Math.max(0, Math.min(BALL_TEXTURE_COUNT - 1, rawRot))
    sprites.ball.gotoAndStop(Math.min(ballFrame, sprites.ball.totalFrames - 1))
    sprites.shadowBall.x = state.ball.x

    // ── Punch ring (view.js:501-511 via computePunchEffect) ──
    const punch = computePunchEffect(state.ball)
    sprites.punch.visible = punch.visible
    if (punch.visible) {
      sprites.punch.x = punch.x
      sprites.punch.y = punch.y
      sprites.punch.width = punch.width
      sprites.punch.height = punch.height
    }

    // ── Ball power-hit effects (authoritative: BE `is_power_hit`) ──
    // Trail sprite positions come from the pure helper so the logic
    // stays testable without a PixiJS stage. Heuristic-based detection
    // was removed 2026-04-12 per PM decision (Mode B): BE is the sole
    // source of truth for `isPowerHit` and the FE ring buffer supplies
    // previous positions when BE doesn't include them inline.
    const trail = computePowerHitTrail(state.ball, ballHistoryRef.current)
    sprites.ballHyper.visible = trail.visible
    sprites.ballTrail.visible = trail.visible
    if (trail.visible) {
      sprites.ballHyper.x = trail.hyper.x
      sprites.ballHyper.y = trail.hyper.y
      sprites.ballTrail.x = trail.trail.x
      sprites.ballTrail.y = trail.trail.y
    }

    // ── Score boards ──
    updateScoreBoard(sprites.scoreBoard1, state.score1)
    updateScoreBoard(sprites.scoreBoard2, state.score2)

    // ── "GAME END" overlay (view.js:622-645 via computeGameEndOverlay) ──
    // The sprite's natural size comes from the loaded texture — use
    // that instead of the scaled `.width/.height` so the sizing math
    // stays idempotent across frames (width assignment would otherwise
    // compound each tick).
    const gameEndTex = sprites.gameEndMessage.texture
    const overlay = computeGameEndOverlay({
      isGameEnded: state.isGameEnded ?? false,
      frameCounter: state.gameEndFrameCounter ?? 0,
      textureWidth: gameEndTex.width,
      textureHeight: gameEndTex.height,
    })
    sprites.gameEndMessage.visible = overlay.visible
    if (overlay.visible) {
      sprites.gameEndMessage.x = overlay.x
      sprites.gameEndMessage.y = overlay.y
      sprites.gameEndMessage.width = overlay.width
      sprites.gameEndMessage.height = overlay.height
    }

    // ── READY blink (view.js:602-615, pikavolley.js:443-444) ──
    // The engine flips `readyMessageVisible` every 5 ticks during
    // `beforeStartOfNextRound`; the FE just mirrors that flag. No
    // FE-side timing needed — the blink cadence is engine-authoritative
    // so a refresh mid-blink picks up the same on/off phase as before.
    sprites.readyMessage.visible = state.readyMessageVisible === true

    // ── Black fade overlay (view.js::FadeInOut, pikavolley.js round
    //     transition flow) ──
    // BE drives `fadeBlackAlpha` in [0, 1] — 0 during active play,
    // ramps up by 1/16 per frame during `afterEndOfRound`, ramps back
    // down by 1/16 during `beforeStartOfNextRound`. We mirror it
    // verbatim and gate `visible` on alpha > 0 so the overlay never
    // intercepts pointer events when the court is fully clear.
    const fadeAlpha = state.fadeBlackAlpha ?? 0
    sprites.fadeOverlay.alpha = fadeAlpha
    sprites.fadeOverlay.visible = fadeAlpha > 0
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

/**
 * Port of view.js:467-483 scale.x branch.
 *
 * `defaultFacing` is +1 for P1 (native sprite orientation) and -1 for
 * P2 (mirrored, since the sheet only stores right-facing poses).
 *
 * During a dive or lie (state 3 / 4), the sheet's single diving pose
 * must be flipped to match which direction the player is diving. The
 * ported engine emits `diving_direction` (-1 / 0 / +1) on every frame
 * — snakeToCamel turns that into `divingDirection` on the WS payload.
 * The original's two-branch rule (view.js:467-474 P1, 476-483 P2)
 * collapses to `divingDirection * sign` when the field is signed,
 * which matches what we get from BE now.
 *
 * When `divingDirection === 0` (no lateral input this tick — rare
 * mid-dive but possible) or the field is absent (pre-port replay),
 * fall through to `defaultFacing` so the sprite doesn't flip to an
 * arbitrary side. The vx-sign fallback that lived here before BE
 * emitted the field has been retired — the engine is now the single
 * source of truth (per 2026-04-17 PM dev-deploy 2084a13d).
 */
function resolvePlayerScaleX(
  p: { state?: number; isDiving: boolean; divingDirection?: number },
  defaultFacing: 1 | -1,
): number {
  const inDiveLike = p.state === 3 || p.state === 4 || p.isDiving
  if (!inDiveLike) return defaultFacing

  const dir = p.divingDirection
  if (dir === 1) return 1
  if (dir === -1) return -1

  return defaultFacing
}

/**
 * Motion-blur afterimage used for the dive/slide pose. Placed a few
 * pixels behind the player along its velocity vector so the slide
 * reads as lateral motion, not a duplicate sprite.
 *
 * The offset distance is intentionally modest (half a body width).
 * Larger offsets separate the two sprites enough that the afterimage
 * reads as a separate character instead of a blur; we only need a
 * ghost, not a second pikachu. Alpha is low so the main sprite stays
 * visually dominant.
 *
 * `scaleX` matches the owning player's facing direction (+1 for P1,
 * -1 for P2) so the afterimage mirrors the same pose orientation.
 */
const DIVE_AFTERIMAGE_OFFSET_PX = 16
const DIVE_AFTERIMAGE_ALPHA = 0.4

function updateDiveAfterimage(
  sprite: AnimatedSprite,
  player: { x: number; y: number; vx: number; vy: number; isDiving: boolean },
  frame: number,
  scaleX: 1 | -1,
): void {
  if (!player.isDiving) {
    sprite.visible = false
    return
  }
  const speed = Math.hypot(player.vx, player.vy)
  // Avoid divide-by-zero on the exact frame a dive begins (vx=vy=0 is
  // unusual but possible between ticks). Fall back to a facing-aligned
  // offset so the afterimage still renders behind the player.
  const dirX = speed > 0 ? -player.vx / speed : -scaleX
  const dirY = speed > 0 ? -player.vy / speed : 0
  sprite.visible = true
  sprite.x = player.x + dirX * DIVE_AFTERIMAGE_OFFSET_PX
  sprite.y = player.y + dirY * DIVE_AFTERIMAGE_OFFSET_PX
  sprite.scale.x = scaleX
  sprite.alpha = DIVE_AFTERIMAGE_ALPHA
  sprite.gotoAndStop(Math.min(frame, sprite.totalFrames - 1))
}

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
