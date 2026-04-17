export interface PlayerState {
  x: number
  y: number
  vx: number
  vy: number
  isJumping: boolean
  isDiving: boolean
  isPowerHitting: boolean
  /**
   * Authoritative animation inputs from the ported physics engine
   * (`backend/game/engine.py::Player.state` / `.frame_number`), matching
   * the original `physics.js::Player.state` field at 0xC0. Optional —
   * pre-port WS payloads and older replays omit them, in which case the
   * FE falls back to the boolean-flag heuristic in `inferPlayerFrame`.
   * `state` values 0-6 map to:
   *   0 idle · 1 jumping · 2 power-hitting · 3 diving (2 frames) ·
   *   4 lying · 5 winning · 6 losing.
   * `divingDirection` (-1 | 0 | 1) flips the sprite while diving/lying,
   * mirroring `view.js::drawPlayersAndBall`'s scale.x branch.
   */
  state?: number
  frameNumber?: number
  divingDirection?: number
  /**
   * Per-player winner / game-ended flags emitted by the engine
   * (`backend/game/engine.py`, BE commit 0ec693ef). `isWinner` is
   * true on the winning player only; `gameEnded` is true on BOTH
   * players for the duration of the 211-frame gameEnd window so
   * either sprite can opt into its own pose timing.
   *
   * The 5/6 win/lose poses themselves come through `state` (5 = win,
   * 6 = lose); these flags are useful for FE-only effects (e.g.
   * "winner highlight") that don't need to peek at top-level
   * isGameEnded + score.
   *
   * Optional for pre-port-state replay decode.
   */
  isWinner?: boolean
  gameEnded?: boolean
}

export interface BallState {
  x: number
  y: number
  vx: number
  vy: number
  rotation: number
  /**
   * Power-hit flag (per-frame). Authoritative source once BE starts
   * emitting it on `training:frame` messages. Optional so the FE can
   * keep shipping before BE lands the field — in the meantime the
   * canvas falls back to its velocity heuristic. Once BE emits it the
   * heuristic gets removed in favor of this flag (see GameCanvas
   * POWER_HIT_SPEED TODO).
   */
  isPowerHit?: boolean
  /**
   * Historical ball positions (t-1 and t-2) matching the original
   * Pikachu Volleyball engine's `previousX/Y` and
   * `previousPreviousX/Y`. Optional — if BE does not include them we
   * maintain a 3-slot ring buffer on the client instead (Mode B, per
   * 2026-04-12 PM decision). Prefer BE values when present since FE
   * buffering drifts under slow-WS conditions.
   */
  previousX?: number
  previousY?: number
  previousPreviousX?: number
  previousPreviousY?: number
  /**
   * Bottom-hit (punch) radial-effect anchor, emitted by BE on the frame
   * a punch lands so the FE can render an expanding ring centered at
   * the impact point. `punchEffectRadius` grows tick-by-tick on the
   * engine side; FE reads the authoritative value each frame rather
   * than animating locally. All three fields are optional until the
   * engine WS payload ships them (AI Engineer track, 2026-04-12). Wire
   * name is snake_case (`punch_effect_x/y/radius`) — snakeToCamel in
   * useTrainingState.handleFrame produces these camelCase keys.
   */
  punchEffectX?: number
  punchEffectY?: number
  punchEffectRadius?: number
}

export interface GameState {
  player1: PlayerState
  player2: PlayerState
  ball: BallState
  score1: number
  score2: number
  frame: number
  /**
   * Top-level scoring/gameEnd signals emitted by the ported engine
   * (`backend/game/engine.py`, serialized at
   * `backend/rl/callbacks.py::_serialize_state`). Optional for
   * compatibility with frames predating the port.
   *
   * - `isRoundOver` latches True from the scoring frame through the
   *   gameEnd window — used to freeze the score overlay.
   * - `isGameEnded` flips True once either score hits MAX_SCORE, and
   *   `gameEndFrameCounter` counts the 211-frame winner/loser pose +
   *   intro-return animation (`pikavolley.js::frameTotal.gameEnd`).
   */
  isRoundOver?: boolean
  isGameEnded?: boolean
  gameEndFrameCounter?: number
  /**
   * Display state-machine fields ported from `pikavolley.js`:
   *   - `round`                  active rally
   *   - `afterEndOfRound`        5-frame fade-to-black after a score
   *   - `beforeStartOfNextRound` 30-frame ready window with a blinking
   *                              "READY" sprite, fade back to clear
   *   - `gameEnd`                211-frame winner/loser pose
   *
   * `slowMotionFramesLeft` decrements during the post-score slow-mo
   * window (max 6). The BE re-emits the same frame several times in
   * a row during this window so the FE renders naturally slow without
   * needing to special-case animation timing.
   *
   * `fadeBlackAlpha` is in [0, 1] and drives a full-screen black
   * overlay sprite (asset `objects/black.png`).
   * `readyMessageVisible` toggles every 5 engine frames during
   * `beforeStartOfNextRound` (`pikavolley.js:443-444`).
   *
   * All optional for compatibility with pre-port replay decode and
   * any frame the engine emits before the state-machine port lands.
   */
  stateName?: string
  slowMotionFramesLeft?: number
  fadeBlackAlpha?: number
  readyMessageVisible?: boolean
  /**
   * Per-frame SFX trigger flags emitted by the ported engine
   * (`backend/rl/callbacks.py::_serialize_state::sounds`, BE dev
   * 2084a13d). Each key is true *only on the frame the sound fires*
   * — the engine resets all flags at the start of every tick
   * (`engine.py:357-364`). `pi` and `pikachu` are intentionally
   * omitted: they are menu-layer sounds in pikavolley.js that the
   * training dashboard never reaches.
   *
   * Wire names are snake_case (`power_hit`, `ball_touches_ground`);
   * snakeToCamel produces the camelCase keys shown here.
   */
  sounds?: {
    pipikachu?: boolean
    pika?: boolean
    chu?: boolean
    powerHit?: boolean
    ballTouchesGround?: boolean
  }
}

export interface TrainingMetrics {
  step: number
  episode: number
  meanReward: number
  winRate: number
  policyLoss: number
  valueLoss: number
}

export interface TrainingStatus {
  state: 'running' | 'stopped' | 'paused'
  currentStep: number
  currentEpisode: number
  /** Current curriculum bot level (1-5). Optional because not every
   *  status broadcast carries it; server emits `bot_level` after
   *  `training:set_level` and on explicit status queries. */
  botLevel?: number
  /** Active training-run identifier. Optional because `training:status`
   *  WS broadcasts omit it (they carry only the delta); populated by
   *  REST `/api/training/status`. Used by the chart hydration path to
   *  scope `/api/training/timeseries` queries to the current run so a
   *  refresh doesn't mix last session's points into this one. */
  experimentId?: string | null
}

/** Raw (step, value) point from GET /api/training/timeseries. Timestamps
 *  are ISO-8601 UTC strings or null if the backing doc lacked one. */
export interface TimeseriesPoint {
  step: number
  value: number
  timestamp: string | null
}

export interface GameRecord {
  /** Mongo `_id` hex string. Unique row key for React. NOT the same as
   *  the replay file stem — see `gameId` below. */
  id: string
  /**
   * UUID4 minted at game-end (`callbacks.py::run_demo_game`) and used
   * as the replay `.msgpack` filename stem (`replay_service.py:30`).
   * The unified history list joins games to replay availability on
   * THIS field, not `id` (the Mongo ObjectId hex). Optional because
   * pre-port replay payloads omit it; the join falls back to `id`
   * when missing so legacy rows still resolve in the rare case the
   * Mongo doc happened to use the UUID as `_id`.
   */
  gameId?: string
  timestamp: string
  /** Bot difficulty (1-5). Optional because the WS `game:result`
   *  broadcast currently omits `bot_level` — the BE enqueues a result
   *  dict without it (backend/rl/callbacks.py:236-242) and the
   *  dispatcher broadcasts that raw dict unchanged
   *  (backend/app/ws/handlers.py:357). REST `/api/games` validates the
   *  field via Pydantic so hydration from REST always has it. Until
   *  BE fixes the enqueue path, live rows from WS can lack this —
   *  consumers must treat it as optional and fall back to "?". See
   *  docs/NOTICE-BE-GAMERESULT-MISSING-FIELDS.md. */
  botLevel?: number
  score1: number
  score2: number
  winner: number
  durationFrames: number
  /**
   * Number of rallies in the game. Optional because BE currently does
   * not track rallies — `LiveFrameCallback._on_step` enqueues a result
   * dict without this field (`backend/rl/callbacks.py:284-292`) and
   * the handler defaults to 0 on save (`backend/app/ws/handlers.py:341`),
   * so every persisted record reads 0. Keeping it optional prevents
   * the FE from confidently rendering "0 rallies" when the truth is
   * "BE never told us"; renderers should use `formatRallyCount` to
   * distinguish missing-data from a legitimate zero.
   *
   * Tracking blocker: see [BE-WAITING] note in
   * `frontend/src/lib/formatGame.ts::formatRallyCount`.
   */
  rallyCount?: number
}

export interface EvalResult {
  modelPath: string
  botLevel: number
  nGames: number
  winRate: number
  avgScore: number
  avgRallyLength: number
}

export interface Hyperparams {
  learning_rate: number
  n_steps: number
  batch_size: number
  gamma: number
  clip_range: number
}

export interface ModelInfo {
  path: string
  sizeBytes: number
}

export interface ReplayInfo {
  gameId: string
  sizeBytes: number
  createdAt: number
}

export interface PaginatedResponse<T> {
  data: T[]
  total: number
  page: number
  limit: number
}

export type WSClientMessageType =
  | 'training:start'
  | 'training:stop'
  | 'training:pause'
  | 'training:resume'
  | 'training:set_level'
  | 'replay:request'

export type WSServerMessageType =
  | 'training:metrics'
  | 'training:frame'
  | 'training:status'
  | 'game:result'
  | 'replay:data'

export type WSMessageType = WSClientMessageType | WSServerMessageType

export interface WSMessage<T = unknown> {
  type: WSMessageType
  payload: T
}

export type ConnectionState = 'connecting' | 'connected' | 'disconnected'
