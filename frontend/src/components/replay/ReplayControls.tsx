<<<<<<< HEAD
import './ReplayControls.css'

=======
>>>>>>> github/yoon/designer
interface ReplayControlsProps {
  isPlaying: boolean
  speed: number
  currentFrame: number
  totalFrames: number
  onTogglePlay: () => void
  onSpeedChange: (speed: number) => void
  onSeek: (frame: number) => void
}

const SPEEDS = [0.5, 1, 2, 4] as const

<<<<<<< HEAD
=======
const btnStyle: React.CSSProperties = {
  padding: '4px 10px',
  border: 'none',
  borderRadius: 4,
  fontFamily: 'monospace',
  fontSize: 12,
  cursor: 'pointer',
}

>>>>>>> github/yoon/designer
export function ReplayControls({
  isPlaying,
  speed,
  currentFrame,
  totalFrames,
  onTogglePlay,
  onSpeedChange,
  onSeek,
}: ReplayControlsProps) {
  return (
<<<<<<< HEAD
    <div className="replay-controls card">
      <div className="replay-controls-bar">
        <button
          onClick={onTogglePlay}
          className="replay-controls-play-btn"
          data-playing={isPlaying}
=======
    <div style={{ background: '#1a1a2e', borderRadius: 8, padding: 12, border: '1px solid #2a2a3e' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 8 }}>
        <button
          onClick={onTogglePlay}
          style={{ ...btnStyle, background: isPlaying ? '#ef4444' : '#22c55e', color: isPlaying ? '#fff' : '#000', minWidth: 64 }}
>>>>>>> github/yoon/designer
        >
          {isPlaying ? 'Pause' : 'Play'}
        </button>

<<<<<<< HEAD
        <div className="replay-controls-speeds">
=======
        <div style={{ display: 'flex', gap: 4 }}>
>>>>>>> github/yoon/designer
          {SPEEDS.map(s => (
            <button
              key={s}
              onClick={() => onSpeedChange(s)}
<<<<<<< HEAD
              className="replay-controls-speed-btn"
              data-active={speed === s}
=======
              style={{
                ...btnStyle,
                background: speed === s ? '#3b82f6' : '#2a2a3e',
                color: speed === s ? '#fff' : '#888',
              }}
>>>>>>> github/yoon/designer
            >
              {s}x
            </button>
          ))}
        </div>

<<<<<<< HEAD
        <span className="replay-controls-frame-info">
=======
        <span style={{ fontSize: 12, color: '#888', marginLeft: 'auto', fontFamily: 'monospace' }}>
>>>>>>> github/yoon/designer
          {currentFrame} / {totalFrames}
        </span>
      </div>

      <input
        type="range"
        min={0}
        max={Math.max(0, totalFrames - 1)}
        value={currentFrame}
        onChange={e => onSeek(Number(e.target.value))}
<<<<<<< HEAD
        className="replay-controls-seek"
=======
        style={{ width: '100%', accentColor: '#3b82f6' }}
>>>>>>> github/yoon/designer
      />
    </div>
  )
}
