<<<<<<< HEAD
import './GameOverlay.css'

=======
>>>>>>> github/yoon/designer
interface GameOverlayProps {
  score1: number
  score2: number
  statusText?: string
  width?: number
}

<<<<<<< HEAD
export function GameOverlay({ score1, score2, statusText }: GameOverlayProps) {
  return (
    <div className="game-overlay">
      <div className="game-overlay-score">
        {score1} : {score2}
      </div>
      {statusText && (
        <div className="game-overlay-status">
=======
export function GameOverlay({ score1, score2, statusText, width = 432 }: GameOverlayProps) {
  return (
    <div
      style={{
        position: 'absolute',
        top: 0,
        left: 0,
        width,
        pointerEvents: 'none',
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        padding: '8px 0',
      }}
    >
      <div
        style={{
          fontSize: 24,
          fontWeight: 'bold',
          fontFamily: 'monospace',
          color: '#fff',
          textShadow: '2px 2px 4px rgba(0,0,0,0.8)',
          letterSpacing: 4,
        }}
      >
        {score1} : {score2}
      </div>
      {statusText && (
        <div
          style={{
            fontSize: 14,
            color: '#ffd700',
            fontFamily: 'monospace',
            textShadow: '1px 1px 2px rgba(0,0,0,0.8)',
            marginTop: 4,
          }}
        >
>>>>>>> github/yoon/designer
          {statusText}
        </div>
      )}
    </div>
  )
}
