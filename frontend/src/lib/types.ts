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
  id: string
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
  rallyCount: number
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
