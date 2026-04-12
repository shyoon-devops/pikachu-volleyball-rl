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
