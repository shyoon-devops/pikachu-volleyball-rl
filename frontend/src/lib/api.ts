import type {
  GameRecord,
  GameState,
  EvalResult,
  ModelInfo,
  PaginatedResponse,
} from './types'

class ApiError extends Error {
  status: number

  constructor(status: number, message: string) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
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

export function getGames(page = 1, limit = 20): Promise<PaginatedResponse<GameRecord>> {
  return request(`/api/games?page=${page}&limit=${limit}`)
}

export function getGame(id: string): Promise<GameRecord> {
  return request(`/api/games/${id}`)
}

export function getReplay(gameId: string): Promise<{ frames: GameState[] }> {
  return request(`/api/replays/${gameId}`)
}

export function getModels(): Promise<ModelInfo[]> {
  return request('/api/models')
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

export function getEvalResults(): Promise<EvalResult[]> {
  return request('/api/evaluation/results')
}

export function getTrainingStatus(): Promise<{ state: string; current_step: number; current_episode: number }> {
  return request('/api/training/status')
}
