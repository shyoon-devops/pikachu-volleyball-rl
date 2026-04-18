import type {
  GameRecord,
  GameState,
  EvalResult,
  ModelInfo,
  PaginatedResponse,
  ReplayInfo,
  TimeseriesPoint,
  TrainingMetrics,
  TrainingStatus,
  TrainingRun,
} from './types'

/**
 * Metric tokens accepted by `/api/training/timeseries`. Keep in sync
 * with `backend/app/api/routes.py::_TIMESERIES_METRICS`. "reward" and
 * "loss" are aliases server-side; we use the canonical 4 to make the
 * merge path unambiguous.
 */
export type TimeseriesMetric =
  | 'reward'
  | 'win_rate'
  | 'policy_loss'
  | 'value_loss'

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

/**
 * List games. `title` filter (BE T5, commit fc38f3d8) restricts to a
 * single training run. Pass `"untitled"` to hit the BE's stable
 * bucket for legacy rows without a title.
 */
export async function getGames(
  page = 1,
  limit = 20,
  title?: string,
): Promise<PaginatedResponse<GameRecord>> {
  const qs = new URLSearchParams({ page: String(page), limit: String(limit) })
  if (title !== undefined && title !== '') qs.set('title', title)
  const raw = await request<{ data: unknown[]; total: number; page: number; limit: number }>(
    `/api/games?${qs.toString()}`,
  )
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

/**
 * List model checkpoints. `title` filter (BE-T8 cd16ef63) scopes the
 * response to one training run — BE slugifies the caller-supplied
 * value and matches against the filename slug, sorted by step desc.
 */
export async function getModels(title?: string, limit?: number): Promise<ModelInfo[]> {
  const qs = new URLSearchParams()
  if (title !== undefined && title !== '') qs.set('title', title)
  if (limit !== undefined) qs.set('limit', String(limit))
  const suffix = qs.toString()
  const raw = await request<Record<string, unknown>>(
    suffix ? `/api/models?${suffix}` : '/api/models',
  )
  const models = Array.isArray(raw.models) ? raw.models : Array.isArray(raw.data) ? raw.data : []
  return snakeToCamel<ModelInfo[]>(models)
}

export interface DeleteModelsResponse {
  deleted: string[]
  failed: Array<{ path: string; reason: string }>
}

/**
 * Bulk-delete checkpoints (BE-T9 dc80b557). Body is `{paths: [...]}`,
 * capped at 100 per request. A 409 means the batch included a file
 * from the active training run — BE rejects the whole request so no
 * partial deletion ever happens; callers should re-surface the list
 * minus protected paths and retry.
 */
export async function deleteModels(paths: string[]): Promise<DeleteModelsResponse> {
  const raw = await request<Record<string, unknown>>('/api/models', {
    method: 'DELETE',
    body: JSON.stringify({ paths }),
  })
  return {
    deleted: Array.isArray(raw.deleted) ? (raw.deleted as string[]) : [],
    failed: Array.isArray(raw.failed)
      ? (raw.failed as Array<{ path: string; reason: string }>)
      : [],
  }
}

/**
 * Kick off an evaluation. BE (commit 8ebbb9f3) switched this from a
 * blocking call to a fire-and-forget job: response is 202 with a
 * `job_id` you poll via `getEvaluationStatus`. 409 still means "another
 * eval is running" and callers should surface it as a busy state, not
 * a generic error.
 */
export async function runEvaluation(
  modelPath: string,
  botLevel: number,
  nGames: number,
): Promise<EvaluationJobAck> {
  const raw = await request<Record<string, unknown>>('/api/evaluation/run', {
    method: 'POST',
    body: JSON.stringify({
      model_path: modelPath,
      bot_level: botLevel,
      n_games: nGames,
    }),
  })
  return snakeToCamel<EvaluationJobAck>(raw)
}

/**
 * Poll an evaluation job by id. Response shape is stable across
 * `state` values; consumers branch on `state`:
 *   - pending / running: show progress
 *   - done:              merge `result` into the results list
 *   - failed:            surface `error`
 */
export async function getEvaluationStatus(jobId: string): Promise<EvaluationJobStatus> {
  const raw = await request<Record<string, unknown>>(`/api/evaluation/status/${jobId}`)
  return snakeToCamel<EvaluationJobStatus>(raw)
}

export interface EvaluationJobAck {
  jobId: string
  state: string
}

export interface EvaluationJobStatus {
  jobId: string
  state: 'pending' | 'running' | 'done' | 'failed'
  progress: { current: number; total: number }
  result: EvalResult | null
  error: string | null
  createdAt?: string | null
  startedAt?: string | null
  finishedAt?: string | null
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

/**
 * One entry from `GET /api/training/titles` (BE T1, commit a7351e57).
 * Used for the HyperparamForm title-input duplicate check and the
 * History page's title autocomplete filter (R6H, future).
 */
export interface TrainingTitleInfo {
  title: string
  experimentId: string
  startedAt: string | null
}

/**
 * Fetch training titles for autocomplete / duplicate-check. `q` is a
 * case-insensitive substring filter; `limit` caps the response size
 * (BE max 500). Returns `[]` when the training_runs collection is
 * uninitialized (BE degrades gracefully to empty rather than 503).
 */
/**
 * Paginated per-title training-run aggregates (BE T4, fc38f3d8).
 * Powers the `/history` drill-down level-1 list. BE sorts desc by
 * `started_at`; FE keeps that order.
 */
export async function getTrainingRuns(
  page = 1,
  limit = 20,
): Promise<PaginatedResponse<TrainingRun>> {
  const raw = await request<{
    data: unknown[]
    total: number
    page: number
    limit: number
  }>(`/api/training/runs?page=${page}&limit=${limit}`)
  return {
    data: snakeToCamel<TrainingRun[]>(raw.data),
    total: raw.total,
    page: raw.page,
    limit: raw.limit,
  }
}

export async function getTrainingTitles(
  q?: string,
  limit = 100,
): Promise<TrainingTitleInfo[]> {
  const params = new URLSearchParams({ limit: String(limit) })
  if (q !== undefined && q !== '') params.set('q', q)
  const raw = await request<Record<string, unknown>>(`/api/training/titles?${params.toString()}`)
  const titles = Array.isArray(raw.titles) ? raw.titles : []
  return snakeToCamel<TrainingTitleInfo[]>(titles)
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
/**
 * Fetch raw per-step training metric points from the BE timeseries
 * endpoint (API spec v0.2.4). Used on mount to hydrate the MetricsChart
 * after a page refresh — the live WS stream then appends new points on
 * top. Unlike `/api/training/metrics/aggregate` (which returns bucketed
 * averages), this endpoint returns the same raw snapshots that the WS
 * stream carries, so REST seed + live stream join 1:1 on `step`.
 *
 * BE caps `limit` at 1000 (validated `ge=1, le=1000`). We request the
 * max by default; `MetricsCallback.log_interval=100` means 1000 points
 * covers 100k training steps — enough for all normal sessions.
 *
 * Points are returned newest-last so callers can extend the chart to
 * the right without sorting. `experimentId` scopes the query to a
 * single run so a refresh mid-session doesn't mix a prior experiment's
 * (step, value) pairs onto the current chart.
 *
 * Best-effort: callers should `.catch(() => [])` — a network failure
 * here just means the chart stays empty until the next WS tick, which
 * is the same fallback we had before hydration existed.
 */
export async function getTimeseries(
  metric: TimeseriesMetric,
  limit = 1000,
  experimentId?: string | null,
): Promise<TimeseriesPoint[]> {
  const params = new URLSearchParams({
    metric,
    limit: String(limit),
  })
  if (experimentId) params.set('experiment_id', experimentId)
  const raw = await request<{ points?: unknown }>(
    `/api/training/timeseries?${params.toString()}`,
  )
  return Array.isArray(raw.points) ? (raw.points as TimeseriesPoint[]) : []
}

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
