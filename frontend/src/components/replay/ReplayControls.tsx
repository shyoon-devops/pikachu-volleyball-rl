import './ReplayControls.css'

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
    <div className="replay-controls">
      <div className="replay-controls__bar">
        <button
          onClick={onTogglePlay}
          className={`btn ${isPlaying ? 'btn-danger' : 'btn-success'}`}
          style={{ minWidth: 72 }}
        >
          {isPlaying ? 'Pause' : 'Play'}
        </button>

        <div className="replay-controls__speeds">
          {SPEEDS.map(s => (
            <button
              key={s}
              onClick={() => onSpeedChange(s)}
              className={`btn btn-ghost ${speed === s ? 'active' : ''}`}
            >
              {s}x
            </button>
          ))}
        </div>

        <span className="replay-controls__frame-counter">
          {currentFrame} / {totalFrames}
        </span>
      </div>

      <input
        type="range"
        min={0}
        max={Math.max(0, totalFrames - 1)}
        value={currentFrame}
        onChange={e => onSeek(Number(e.target.value))}
        className="replay-controls__seekbar"
      />
    </div>
  )
}
