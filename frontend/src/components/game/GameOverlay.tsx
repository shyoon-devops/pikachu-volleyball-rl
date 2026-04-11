import './GameOverlay.css'

interface GameOverlayProps {
  score1: number
  score2: number
  statusText?: string
  width?: number
}

export function GameOverlay({ score1, score2, statusText }: GameOverlayProps) {
  return (
    <div className="game-overlay">
      <div className="game-overlay-score">
        {score1} : {score2}
      </div>
      {statusText && (
        <div className="game-overlay-status">
          {statusText}
        </div>
      )}
    </div>
  )
}
