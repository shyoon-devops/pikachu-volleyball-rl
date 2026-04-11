import './GameOverlay.css'

interface GameOverlayProps {
  score1: number
  score2: number
  statusText?: string
  width?: number
}

export function GameOverlay({ score1, score2, statusText, width = 432 }: GameOverlayProps) {
  return (
    <div className="game-overlay" style={{ width }}>
      <div className="scoreboard">
        <div className="score-side">
          <span className="score-label score-label--p1">P1</span>
          <span className="score-value score-value--p1">{String(score1).padStart(2, '0')}</span>
        </div>
        <span className="score-separator">:</span>
        <div className="score-side">
          <span className="score-value score-value--p2">{String(score2).padStart(2, '0')}</span>
          <span className="score-label score-label--p2">P2</span>
        </div>
      </div>
      {statusText && (
        <div className="game-status-text">{statusText}</div>
      )}
    </div>
  )
}
