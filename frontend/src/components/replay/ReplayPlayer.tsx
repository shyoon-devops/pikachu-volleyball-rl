import { useState, useEffect, useRef, useCallback, useMemo } from 'react'
import { useParams, useLocation, Link } from 'react-router-dom'
import { GameCanvas } from '../game/GameCanvas'
import { GameOverlay } from '../game/GameOverlay'
import { ReplayControls } from './ReplayControls'
import { getReplay, getGames } from '../../lib/api'
import { formatBotLevel, formatRallyCount } from '../../lib/formatGame'
import { formatKstDateTime } from '../../lib/formatTime'
import type { GameRecord, GameState } from '../../lib/types'
import './ReplayPlayer.css'

const FPS = 30

export function ReplayPlayer() {
  const { id } = useParams<{ id: string }>()
  const location = useLocation()
  // FC-R7J: callers (ReplayList's Watch button) ship the originating
  // path via `location.state.from` so Back returns to the exact drill-
  // down — e.g. /history/my-run — instead of the top-level /history.
  // Fallback to /history keeps the flow intact for deep-link traffic
  // (bookmarks / shared URLs) where there's no referrer in state.
  const backTo =
    (location.state as { from?: string } | null)?.from ?? '/history'
  const [frames, setFrames] = useState<GameState[]>([])
  const [currentIndex, setCurrentIndex] = useState(0)
  const [isPlaying, setIsPlaying] = useState(false)
  const [speed, setSpeed] = useState(1)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  // GameRecord lookup for the bottom metadata strip (V4 user request,
  // 2026-04-18). Optional — the strip degrades gracefully to
  // frame-derived values when this fetch fails or returns no match.
  const [meta, setMeta] = useState<GameRecord | null>(null)
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null)

  useEffect(() => {
    if (!id) return
    let cancelled = false
    getReplay(id)
      .then(res => {
        if (cancelled) return
        setFrames(res.frames)
        setCurrentIndex(0)
        setIsPlaying(false)
        setError(null)
      })
      .catch(err => {
        if (cancelled) return
        const msg = err instanceof Error ? err.message : 'Failed to load replay'
        setError(msg.includes('not found') || msg.includes('404')
          ? 'Replay data not available for this game. Replays are only saved during training sessions.'
          : msg,
        )
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => { cancelled = true }
  }, [id])

  /**
   * Best-effort GameRecord lookup so the metadata strip can show
   * `botLevel`, `rallyCount`, and the original game timestamp — none
   * of which are present in the per-frame `GameState` payloads stored
   * in the replay msgpack.
   *
   * The route `/api/games/{id}` only accepts the Mongo ObjectId hex,
   * but the URL we navigate from in `ReplayList` carries the UUID4
   * `gameId` (the replay file stem). There's no FE-callable endpoint
   * that takes the UUID directly today, so we list page 1 of /games
   * (default 100 records, 5s server-side TTL cache) and find the
   * matching record client-side. Misses (game older than the first
   * page or game record missing from Mongo) silently fall through;
   * the metadata strip downgrades to frame-derived values only.
   */
  useEffect(() => {
    if (!id) return
    let cancelled = false
    getGames(1, 100)
      .then(res => {
        if (cancelled) return
        const match = res.data.find(g => g.gameId === id || g.id === id) ?? null
        setMeta(match)
      })
      .catch(() => { /* silent — strip falls back to frame-derived */ })
    return () => { cancelled = true }
  }, [id])

  const clearTimer = useCallback(() => {
    if (timerRef.current !== null) {
      clearInterval(timerRef.current)
      timerRef.current = null
    }
  }, [])

  useEffect(() => {
    clearTimer()
    if (!isPlaying || frames.length === 0) return

    const interval = 1000 / (FPS * speed)
    timerRef.current = setInterval(() => {
      setCurrentIndex(prev => {
        if (prev >= frames.length - 1) {
          setIsPlaying(false)
          return prev
        }
        return prev + 1
      })
    }, interval)

    return clearTimer
  }, [isPlaying, speed, frames.length, clearTimer])

  const handleTogglePlay = useCallback(() => {
    if (currentIndex >= frames.length - 1) {
      setCurrentIndex(0)
    }
    setIsPlaying(prev => !prev)
  }, [currentIndex, frames.length])

  const handleSeek = useCallback((frame: number) => {
    setCurrentIndex(frame)
    setIsPlaying(false)
  }, [])

  const stepFrame = useCallback((delta: number) => {
    setCurrentIndex(prev => Math.max(0, Math.min(frames.length - 1, prev + delta)))
    setIsPlaying(false)
  }, [frames.length])

  useEffect(() => {
    if (frames.length === 0) return

    const handleKeyDown = (e: KeyboardEvent) => {
      const tag = (e.target as HTMLElement).tagName
      if (tag === 'INPUT' || tag === 'SELECT' || tag === 'TEXTAREA') return

      // Scrubbing UX: horizontal arrows step one frame, vertical arrows
      // jump ten frames — matches common video-editor muscle memory.
      switch (e.code) {
        case 'Space':
          e.preventDefault()
          handleTogglePlay()
          break
        case 'ArrowLeft':
          e.preventDefault()
          stepFrame(-1)
          break
        case 'ArrowRight':
          e.preventDefault()
          stepFrame(1)
          break
        case 'ArrowDown':
          e.preventDefault()
          stepFrame(-10)
          break
        case 'ArrowUp':
          e.preventDefault()
          stepFrame(10)
          break
        case 'Home':
          e.preventDefault()
          setCurrentIndex(0)
          setIsPlaying(false)
          break
        case 'End':
          e.preventDefault()
          setCurrentIndex(Math.max(0, frames.length - 1))
          setIsPlaying(false)
          break
        case 'Digit0':
          setSpeed(0.5)
          break
        case 'Digit1':
          setSpeed(1)
          break
        case 'Digit2':
          setSpeed(2)
          break
        case 'Digit3':
          setSpeed(4)
          break
      }
    }

    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [frames.length, handleTogglePlay, stepFrame])

  const currentFrame = frames[currentIndex] ?? null
  const score1 = currentFrame?.score1 ?? 0
  const score2 = currentFrame?.score2 ?? 0

  /**
   * Frame-derived metadata — works without the GameRecord fetch and
   * is the authoritative source for fields the record can't add
   * (final score is the absolute truth from the replay's last frame,
   * not the DB record which may have a slight off-by-one in edge
   * cases). REST `meta` fills in fields no frame carries (botLevel,
   * rallyCount, timestamp).
   */
  const summary = useMemo(() => {
    const last = frames[frames.length - 1] ?? null
    const finalScore1 = last?.score1 ?? meta?.score1 ?? 0
    const finalScore2 = last?.score2 ?? meta?.score2 ?? 0
    const winner =
      meta?.winner ??
      (finalScore1 > finalScore2 ? 1 : finalScore2 > finalScore1 ? 2 : 0)
    const durationFrames =
      last?.frame ?? meta?.durationFrames ?? frames.length
    return {
      finalScore1,
      finalScore2,
      winner,
      durationFrames,
    }
  }, [frames, meta])

  if (loading) {
    return <div className="replay-player-loading">Loading replay...</div>
  }

  if (error) {
    return (
      <div className="replay-player-error-wrapper">
        <div className="replay-player-error alert-error">{error}</div>
        <Link to={backTo} className="replay-player-error-back">Back to History</Link>
      </div>
    )
  }

  return (
    <div className="replay-player">
      <div className="replay-player-header">
        <Link to={backTo} className="replay-player-back">&larr; Back</Link>
        <h2 className="replay-player-title">Replay: {id}</h2>
      </div>

      <div className="replay-player-game">
        <GameCanvas gameState={currentFrame} width={648} height={456} />
        <GameOverlay score1={score1} score2={score2} width={648} />
      </div>

      <ReplayControls
        isPlaying={isPlaying}
        speed={speed}
        currentFrame={currentIndex}
        totalFrames={frames.length}
        onTogglePlay={handleTogglePlay}
        onSpeedChange={setSpeed}
        onSeek={handleSeek}
      />

      <dl className="replay-player-meta" aria-label="Replay metadata">
        <div className="replay-player-meta-item">
          <dt>Bot Level</dt>
          <dd>{formatBotLevel(meta?.botLevel)}</dd>
        </div>
        <div className="replay-player-meta-item">
          <dt>Final Score</dt>
          <dd>
            <span className="score-p1">{summary.finalScore1}</span>
            {' : '}
            <span className="score-p2">{summary.finalScore2}</span>
          </dd>
        </div>
        <div className="replay-player-meta-item">
          <dt>Winner</dt>
          <dd className={summary.winner === 1 ? 'winner-agent' : summary.winner === 2 ? 'winner-bot' : ''}>
            {summary.winner === 1 ? 'RL Agent' : summary.winner === 2 ? 'Bot' : '—'}
          </dd>
        </div>
        <div className="replay-player-meta-item">
          <dt>Duration</dt>
          <dd className="text-muted">{summary.durationFrames} frames</dd>
        </div>
        <div className="replay-player-meta-item">
          <dt>Rallies</dt>
          <dd className="text-muted">{formatRallyCount(meta?.rallyCount)}</dd>
        </div>
        {meta?.timestamp && (
          <div className="replay-player-meta-item">
            <dt>Recorded</dt>
            <dd className="text-muted">{formatKstDateTime(meta.timestamp)}</dd>
          </div>
        )}
        {meta?.experimentId && (
          <div className="replay-player-meta-item replay-player-meta-item--wide">
            <dt>Experiment</dt>
            <dd className="text-muted text-mono">{meta.experimentId}</dd>
          </div>
        )}
      </dl>
    </div>
  )
}
