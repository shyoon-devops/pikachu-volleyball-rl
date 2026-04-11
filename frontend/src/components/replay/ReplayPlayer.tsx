import { useState, useEffect, useRef, useCallback } from 'react'
import { useParams, Link } from 'react-router-dom'
import { GameCanvas } from '../game/GameCanvas'
import { GameOverlay } from '../game/GameOverlay'
import { ReplayControls } from './ReplayControls'
import { getReplay } from '../../lib/api'
import type { GameState } from '../../lib/types'
import './ReplayPlayer.css'

const FPS = 30

export function ReplayPlayer() {
  const { id } = useParams<{ id: string }>()
  const [frames, setFrames] = useState<GameState[]>([])
  const [currentIndex, setCurrentIndex] = useState(0)
  const [isPlaying, setIsPlaying] = useState(false)
  const [speed, setSpeed] = useState(1)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
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
        setError(err instanceof Error ? err.message : 'Failed to load replay')
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
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

  const handleTogglePlay = () => {
    if (currentIndex >= frames.length - 1) {
      setCurrentIndex(0)
    }
    setIsPlaying(prev => !prev)
  }

  const handleSeek = (frame: number) => {
    setCurrentIndex(frame)
    setIsPlaying(false)
  }

  const currentFrame = frames[currentIndex] ?? null
  const score1 = currentFrame?.score1 ?? 0
  const score2 = currentFrame?.score2 ?? 0

  if (loading) {
    return <div className="replay-player-loading">Loading replay...</div>
  }

  if (error) {
    return (
      <div className="replay-player-error-wrapper">
        <div className="replay-player-error alert-error">{error}</div>
        <Link to="/history" className="replay-player-error-back">Back to History</Link>
      </div>
    )
  }

  return (
    <div className="replay-player">
      <div className="replay-player-header">
        <Link to="/history" className="replay-player-back">&larr; Back</Link>
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
    </div>
  )
}
