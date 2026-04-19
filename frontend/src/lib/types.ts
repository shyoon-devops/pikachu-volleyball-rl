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
  /**
   * Human-authored training title (BE T1, commit a7351e57). BE echoes
   * the final title — either the user's value or an auto-generated
   * `run-{adj}-{noun}-{4hex}` — in the `training:start` response and
   * on `GET /api/training/status`. Optional because legacy pre-T1
   * sessions have no title.
   */
  title?: string | null
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
   * Training experiment id this game was played under
   * (`backend/app/models/schemas.py::GameRecord.experiment_id`).
   * Optional because legacy/manual records may lack the field; the
   * replay metadata strip only renders it when present.
   */
  experimentId?: string
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
  /**
   * Parallel env that produced this game. BE
   * (`backend/rl/callbacks.py::DrainResultsCallback._on_step`) emits
   * the field as a STRING: `"0".."7"` for parallel gradient envs,
   * `"demo"` for the standalone demo game. Stringified so both
   * families share a single Mongo column.
   *
   * FE keeps the string form verbatim; `formatEnvId` and the env
   * filter drop-down handle both variants. Optional because
   * pre-port records lack the field entirely.
   */
  envId?: string
  /**
   * Denormalised training title snapshot (BE T1, commit a7351e57).
   * Preserved at save time so a later rename on the training run
   * doesn't orphan history rows. Optional because pre-T1 records
   * have no title — FE renders `—` in those cells.
   */
  title?: string | null
  /**
   * Monotonic episode number at game-end, sourced from
   * `TrainingManager.current_episode` (`backend/rl/trainer.py`).
   * Optional: BE does NOT include it on per-game result broadcasts
   * today (only on REST `/api/training/status` for the LIVE
   * counter). Rows without it render as `—` in the column.
   *
   * [BE-WAITING] Add `"episode": mgr.current_episode` to the payload
   * dict in `callbacks.py::DrainResultsCallback._on_step` alongside
   * `env_id` so the FE column can light up per row.
   */
  episode?: number
  /**
   * Opponent identifier for this match (v2.x Sprint 1).
   *
   * `null` / undefined means this game was fought against the rule
   * bot at `botLevel` — the Recent Games Opponent column renders
   * `Rule L{botLevel}` in that case (today's normal path).
   *
   * When BE-impl ships the self-play broadcast, this carries the
   * opponent checkpoint id (the league pool slug, e.g.
   * `run-baseline__abc12345__200000`) so the FE can render the
   * `policy_<exp8>_<step>` chip variant. [BE-WAITING] for the
   * `game:result` payload to carry this field.
   */
  opponentCheckpointId?: string | null
}

/**
 * Per-title training run summary from `GET /api/training/runs`
 * (BE T4, commit fc38f3d8). Powers the history page's level-1
 * drill-down list.
 */
export interface TrainingRun {
  title: string
  experimentId: string | null
  startedAt: string | null
  endedAt: string | null
  totalGames: number
  winRate: number
  avgRallyLength: number
  /** BE emits "running" when the live training manager's current
   *  title matches this row; "done" otherwise. Legacy records with
   *  no status default to "done". */
  status: 'running' | 'done' | string
  /**
   * Snapshot of the hyperparameters the run was launched with
   * (FC-R8b). `null` / undefined means the run record pre-dates
   * BE-T10 (no persisted hyperparams) — the FE renders a
   * placeholder summary in that case.
   *
   * [BE-WAITING] Populated once BE-T10 teaches `title_service.
   * register()` to persist the HyperparamFormSubmission payload on
   * `training_runs`, and extends `aggregate_by_title` to carry it
   * forward. Shape mirrors `Hyperparams` (the 10 canonical PPO
   * knobs) so the FE can render without coupling to BE snake_case
   * at the display layer — `snakeToCamel` handles the wire format.
   */
  hyperparams?: Partial<Hyperparams> | null
}

export interface EvalResult {
  modelPath: string
  botLevel: number
  nGames: number
  winRate: number
  avgScore: number
  avgRallyLength: number
  /**
   * ISO-8601 UTC timestamp, set by BE Pydantic default on the
   * `EvaluationRecord` (`backend/app/models/schemas.py:58`).
   * Optional on the FE side because older stored records may be
   * missing the field; `formatKstDateTime` falls back to an
   * em-dash when absent.
   */
  timestamp?: string
  /**
   * Training run this eval belongs to (BE EvaluationRecord's
   * `training_title`). Populated by BE when the eval was launched
   * from the /runs drill-down; older results may omit it. The FE
   * uses this to filter the Evaluation sub-tab's results history
   * down to the current run.
   */
  trainingTitle?: string | null
}

/**
 * Extended hyperparam set. BE (`WsTrainingStartPayload`, commit
 * cc4daaf3) accepts some fields top-level and some inside the
 * `hyperparams` blob; the FE form keeps them flat and the submit
 * path unbundles via `HYPERPARAM_WIRE_POSITION` in
 * `frontend/src/lib/hyperparams.ts`.
 */
export interface Hyperparams {
  learning_rate: number
  n_steps: number
  batch_size: number
  gamma: number
  clip_range: number
  /** Training length in PPO timesteps. Top-level on the wire. */
  total_timesteps: number
  /** Parallel env count (SubprocVecEnv). Top-level on the wire. */
  n_envs: number
  /** PPO epochs per rollout. Top-level on the wire. */
  n_epochs: number
  /** Entropy bonus coefficient. Top-level on the wire. */
  ent_coef: number
  /** GAE lambda. Top-level on the wire. */
  gae_lambda: number
}

export interface ModelInfo {
  path: string
  sizeBytes: number
  /**
   * Enriched fields (BE-T8 cd16ef63). Older callers kept reading
   * `path`/`sizeBytes`; new surfaces (eval drill-down) read these.
   *
   * `step` is the PPO timestep parsed from the filename. The string
   * `"final"` is coerced server-side to the sentinel `10**12` so it
   * sorts above every real step in a desc view.
   *
   * `slug` / `title` are the lowercased training-title slug; both hold
   * the same value — `title` is the FE-friendly name, `slug` is kept
   * for debugging parity with BE's filename parser. Legacy
   * `{exp_id}/final` files land without a slug and return null.
   */
  filename?: string
  slug?: string | null
  title?: string | null
  step?: number | null
  createdAt?: string
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
  | 'training:env_frame'
  | 'training:league_update'
  | 'training:update_start'
  | 'training:update_end'
  | 'game:result'
  | 'replay:data'

/**
 * Per-env frame broadcast (BE commit 65dd7336). Emitted every
 * `broadcast_interval` vec steps while training is running, carrying
 * one payload per parallel env. The FE's batch tab bar subscribes
 * and renders only the currently-selected env on the canvas.
 */
export interface EnvFramePayload {
  /** 0-indexed parallel env id (0..n_envs-1). */
  envId: number
  /** Full per-env GameState snapshot. Same shape as `training:frame`. */
  frame: GameState
  /** Top-level score pair [p1, p2], duplicated from `frame.score{1,2}`
   *  for cheap chip rendering without reaching into the frame. */
  score: [number, number]
  /** Engine state-machine name: 'round' | 'afterEndOfRound' |
   *  'beforeStartOfNextRound' | 'gameEnd' | 'live' (default). Drives
   *  the chip's status dot colour (warning / success / danger). */
  stateName: string
  /** Training step at broadcast time. Useful for ordering snapshots. */
  step: number
}

export type WSMessageType = WSClientMessageType | WSServerMessageType

/**
 * WS message envelope, discriminated by `type` (A6, 2026-04-19).
 *
 * The generic `T` narrows the literal `type` field — every subscriber
 * pins its own topic so the compiler can later (with zod, A6 step 2)
 * exhaustively check payload schemas without a runtime cast.
 *
 * Payload remains `unknown` here on purpose: the wire shape is BE
 * snake_case while domain types live in camelCase, and the snake→camel
 * transform happens in the receiving handler. The zod schemas in
 * `lib/ws-schemas.ts` carry that transform AND the runtime check; this
 * envelope only owns topic discrimination.
 */
export type WSMessage<T extends WSMessageType = WSMessageType> = {
  type: T
  payload: unknown
}

export type ConnectionState = 'connecting' | 'connected' | 'disconnected'

// ── Self-play league (v2.x Sprint 1) ─────────────────────────────
// Contracts tracked with ADR-0014 + docs/design/SELF-PLAY-UX.md.

/** Training-mode toggle (wire value). ADR-0014 §1. */
export type TrainingMode = 'bot_ladder' | 'self_play'

/**
 * Self-play sampling strategies (ADR-0014 §2). Only consumed when
 * `training_mode === 'self_play'`. `pfsp` is the default (weights
 * opponents by `(1 − winrate)^2`); `elo_proximity` matches by
 * nearby Elo; `uniform` draws unbiased.
 */
export type LeagueSampling = 'uniform' | 'elo_proximity' | 'pfsp'

/** Source label for a pool entry (ADR-0014 §1). `anchor` rows are
 *  the fixed-Elo L1/L3/L5 rule baselines that never update. */
export type LeagueCheckpointSource = 'training' | 'v1_legacy' | 'anchor'

/** One row of the league pool. Wire shape from BE-T4 league API is
 *  snake_case; `snakeToCamel` produces these camelCase keys. */
export interface LeagueCheckpoint {
  id: string
  elo: number
  wins: number
  losses: number
  games: number
  /** ISO-8601 UTC admission timestamp. */
  admittedAt: string
  step?: number | null
  experimentId?: string | null
  source: LeagueCheckpointSource
}

/** Envelope shape for `GET /api/league/standings`. */
export interface LeagueStandings {
  top: LeagueCheckpoint[]
  championId: string | null
  generation: number
  poolSize: number
  totalCheckpoints: number
}

/**
 * Payloads for the PPO gradient-update lifecycle (Fix-A FE).
 * BE emits `training:update_start` when the rollout finishes and
 * the PPO `.learn()` call begins; `training:update_end` fires when
 * the first post-update frame is ready. Both carry the owning
 * experiment id so consumers can ignore stale events from a
 * previous session. `step` may be null for legacy / edge-case
 * emissions; the overlay renders without it in that case.
 */
export interface TrainingUpdateStartPayload {
  experimentId: string
  step?: number | null
}

export interface TrainingUpdateEndPayload {
  experimentId: string
  step?: number | null
}

/** Payload for the `training:league_update` WS broadcast
 *  (every LEAGUE_BROADCAST_INTERVAL matches, BE handlers.py). */
export interface LeagueUpdatePayload {
  topN: LeagueCheckpoint[]
  poolSize: number
  championId: string | null
  generation: number
  totalMatches: number
  sinceLastBroadcast: number
  /** Recent match summaries for the Recent Matches panel. */
  recent?: Array<{
    opponentId: string
    winner: string | null
    duration: number
    deltaElo: number
  }>
}
