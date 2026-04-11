import { useState, useEffect, useRef, useCallback } from 'react'
import { useParams, Link } from 'react-router-dom'
import { GameCanvas } from '../game/GameCanvas'
import { GameOverlay } from '../game/GameOverlay'
import { ReplayControls } from './ReplayControls'
import { getReplay } from '../../lib/api'
import type { GameState } from '../../lib/types'
<<<<<<< HEAD
import './ReplayPlayer.css'
=======
>>>>>>> github/yoon/designer

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
<<<<<<< HEAD
    return <div className="replay-player-loading">Loading replay...</div>
=======
    return (
      <div style={{ padding: 24, textAlign: 'center', color: '#888' }}>Loading replay...</div>
    )
>>>>>>> github/yoon/designer
  }

  if (error) {
    return (
<<<<<<< HEAD
      <div className="replay-player-error-wrapper">
        <div className="replay-player-error alert-error">{error}</div>
        <Link to="/history" className="replay-player-error-back">Back to History</Link>
=======
      <div style={{ padding: 24, maxWidth: 600, margin: '0 auto' }}>
        <div style={{ padding: 12, background: '#3a1a1a', border: '1px solid #5a2a2a', borderRadius: 6, color: '#f87171', fontSize: 13, marginBottom: 16 }}>
          {error}
        </div>
        <Link to="/history" style={{ color: '#3b82f6', fontSize: 13 }}>Back to History</Link>
>>>>>>> github/yoon/designer
      </div>
    )
  }

  return (
<<<<<<< HEAD
    <div className="replay-player">
      <div className="replay-player-header">
        <Link to="/history" className="replay-player-back">&larr; Back</Link>
        <h2 className="replay-player-title">Replay: {id}</h2>
      </div>

      <div className="replay-player-game">
=======
    <div style={{ maxWidth: 700, margin: '0 auto', padding: 24, display: 'flex', flexDirection: 'column', gap: 16 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
        <Link to="/history" style={{ color: '#3b82f6', fontSize: 13, textDecoration: 'none' }}>
          &larr; Back
        </Link>
        <h2 style={{ fontSize: 16, color: '#ccc', margin: 0 }}>Replay: {id}</h2>
      </div>

      <div style={{ position: 'relative' }}>
>>>>>>> github/yoon/designer
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
