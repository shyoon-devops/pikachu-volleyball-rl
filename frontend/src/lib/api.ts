import type {
  GameRecord,
  GameState,
  EvalResult,
  ModelInfo,
  PaginatedResponse,
  ReplayInfo,
  TrainingMetrics,
  TrainingStatus,
} from './types'

class ApiError extends Error {
  status: number

  constructor(status: number, message: string) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

function snakeToCamelStr(s: string): string {
  return s.replace(/_([a-z])/g, (_, c: string) => c.toUpperCase())
}

export function snakeToCamel<T>(obj: unknown): T {
  if (Array.isArray(obj)) {
    return obj.map(item => snakeToCamel(item)) as T
  }
  if (obj !== null && typeof obj === 'object') {
    const result: Record<string, unknown> = {}
    for (const [key, value] of Object.entries(obj as Record<string, unknown>)) {
      const camelKey = key === '_id' ? 'id' : snakeToCamelStr(key)
      result[camelKey] = snakeToCamel(value)
    }
    return result as T
  }
  return obj as T
}

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  })

  if (!response.ok) {
    const text = await response.text().catch(() => 'Unknown error')
    throw new ApiError(response.status, text)
  }

  return response.json() as Promise<T>
}

export async function getGames(page = 1, limit = 20): Promise<PaginatedResponse<GameRecord>> {
  const raw = await request<{ data: unknown[]; total: number; page: number; limit: number }>(`/api/games?page=${page}&limit=${limit}`)
  return {
    data: snakeToCamel<GameRecord[]>(raw.data),
    total: raw.total,
    page: raw.page,
    limit: raw.limit,
  }
}

export async function getGame(id: string): Promise<GameRecord> {
  const raw = await request<unknown>(`/api/games/${id}`)
  return snakeToCamel<GameRecord>(raw)
}

export async function getReplay(gameId: string): Promise<{ frames: GameState[] }> {
  const raw = await request<Record<string, unknown>>(`/api/replays/${gameId}`)
  const frames = Array.isArray(raw.frames) ? raw.frames : Array.isArray(raw) ? raw : []
  return { frames: snakeToCamel<GameState[]>(frames) }
}

export async function getModels(): Promise<ModelInfo[]> {
  const raw = await request<Record<string, unknown>>('/api/models')
  const models = Array.isArray(raw.models) ? raw.models : Array.isArray(raw.data) ? raw.data : []
  return snakeToCamel<ModelInfo[]>(models)
}

export function runEvaluation(modelPath: string, botLevel: number, nGames: number): Promise<{ id: string }> {
  return request('/api/evaluation/run', {
    method: 'POST',
    body: JSON.stringify({
      model_path: modelPath,
      bot_level: botLevel,
      n_games: nGames,
    }),
  })
}

export async function getEvalResults(): Promise<EvalResult[]> {
  const raw = await request<Record<string, unknown>>('/api/evaluation/results')
  const data = Array.isArray(raw.data) ? raw.data : Array.isArray(raw) ? raw : []
  return snakeToCamel<EvalResult[]>(data)
}

export async function getAvailableReplays(): Promise<ReplayInfo[]> {
  const raw = await request<Record<string, unknown>>('/api/replays')
  const replays = Array.isArray(raw.replays) ? raw.replays : []
  return snakeToCamel<ReplayInfo[]>(replays)
}

export async function getTrainingStatus(): Promise<TrainingStatus> {
  const raw = await request<unknown>('/api/training/status')
  return snakeToCamel<TrainingStatus>(raw)
}

/**
 * Training command REST endpoints (API spec v0.2.4).
 *
 * Backend is adding these alongside the existing WS channel. Until
 * they ship everywhere, the frontend fires *both* REST and WS so the
 * command still lands whichever path is live; either call returning
 * 404 is treated as "this endpoint isn't deployed yet" — not an error
 * the user needs to see. See useTrainingState.send() for the caller.
 *
 * All four are best-effort: callers MUST swallow rejections (or use
 * the `*Safe` helpers below) — the WS path plus the optimistic UI
 * update are the user-visible guarantee.
 */
export function stopTraining(): Promise<void> {
  return request('/api/training/stop', { method: 'POST' })
}

export function pauseTraining(): Promise<void> {
  return request('/api/training/pause', { method: 'POST' })
}

export function resumeTraining(): Promise<void> {
  return request('/api/training/resume', { method: 'POST' })
}

export function patchTrainingLevel(level: number): Promise<{ level: number }> {
  return request('/api/training/level', {
    method: 'PATCH',
    body: JSON.stringify({ level }),
  })
}

/**
 * Live game-canvas frame for refresh recovery.
 *
 * Returns null if training isn't running (backend responds 404 or a
 * null body) — the UI should show a loading/idle placeholder and wait
 * for the first WS `training:frame` instead of crashing.
 */
export async function getCurrentFrame(): Promise<GameState | null> {
  try {
    const raw = await request<unknown>('/api/training/current_frame')
    if (raw === null || raw === undefined) return null
    return snakeToCamel<GameState>(raw)
  } catch (err) {
    if (err instanceof ApiError && err.status === 404) return null
    throw err
  }
}

/**
 * Fetch the most-recent completed games for the Dashboard's "Recent
 * Games" panel. WebSocket `game:result` pushes the live stream; this
 * REST call seeds the list on mount / reconnect so a refresh doesn't
 * wipe the panel.
 */
export async function getRecentGames(limit = 20): Promise<GameRecord[]> {
  const resp = await getGames(1, limit)
  return resp.data
}

interface MetricsAggregateBucket {
  bucket_start?: string
  count?: number
  step_max?: number | null
  avg_mean_reward?: number | null
  avg_win_rate?: number | null
  avg_policy_loss?: number | null
  avg_value_loss?: number | null
}

interface MetricsAggregateResponse {
  data?: MetricsAggregateBucket[]
  count?: number
  bucket?: string
  experiment_id?: string | null
}

/**
 * Fetch time-bucketed training metrics and map them to the
 * `TrainingMetrics` shape the charts consume. Used on mount /
 * reconnect so a refresh doesn't wipe the graphs — the live stream
 * continues to append per-step samples over WebSocket on top of this
 * historical seed.
 *
 * The aggregate endpoint groups metrics into fixed-width time buckets
 * and reports averages; `step_max` per bucket is used as the x-axis
 * value so the chart reflects training progress even when cadence is
 * irregular. Unknown / null fields collapse to 0 rather than blowing
 * up the chart pipeline.
 */
export async function getMetricsHistory(
  bucket: '1m' | '5m' | '1h' = '1m',
): Promise<TrainingMetrics[]> {
  const params = new URLSearchParams({ bucket })
  const raw = await request<MetricsAggregateResponse>(
    `/api/training/metrics/aggregate?${params.toString()}`,
  )
  const buckets = Array.isArray(raw.data) ? raw.data : []
  return buckets.map<TrainingMetrics>(b => ({
    step: Number(b.step_max ?? 0),
    episode: 0,
    meanReward: Number(b.avg_mean_reward ?? 0),
    winRate: Number(b.avg_win_rate ?? 0),
    policyLoss: Number(b.avg_policy_loss ?? 0),
    valueLoss: Number(b.avg_value_loss ?? 0),
  }))
}
