export interface PlayerState {
  x: number
  y: number
  vx: number
  vy: number
  isJumping: boolean
  isDiving: boolean
  isPowerHitting: boolean
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
}

export interface GameState {
  player1: PlayerState
  player2: PlayerState
  ball: BallState
  score1: number
  score2: number
  frame: number
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
}

export interface GameRecord {
  id: string
  timestamp: string
  botLevel: number
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
