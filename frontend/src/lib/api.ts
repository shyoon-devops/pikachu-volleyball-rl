import type {
  GameRecord,
  GameState,
  EvalResult,
  ModelInfo,
  PaginatedResponse,
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

export async function getTrainingStatus(): Promise<TrainingStatus> {
  const raw = await request<unknown>('/api/training/status')
  return snakeToCamel<TrainingStatus>(raw)
}
